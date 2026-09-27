"""
Frontend Bridge Layer for Member 4.
FastAPI async bridge relaying event bus topics to the browser via WebSockets (ws://localhost:8000/ws/events)
and exposing REST endpoints for fault injection, feature importance, and reconciliation logs.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.8 and Plan_docs/member-4-frontend-eval.md.

WebSocket shape: { "type": "<topic>", "payload": {...} }
Topics: "telemetry.reading", "alert.raised", "reroute.completed"
"""
import asyncio
from dataclasses import asdict
import json
import logging
import threading
import time
from typing import Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from shared.config import (
    EVENTS_LOG_FILE,
    MODELS_DIR,
    POLL_INTERVAL_SEC,
    PROJECT_ROOT,
    TOPIC_ALERT,
    TOPIC_REROUTE,
    TOPIC_TELEMETRY,
)
from shared.event_bus import bus
from network_sim.topology import build_topology
from network_sim.fault_injector import FaultInjector
from network_sim.traffic import TrafficSimulator
from telemetry.snmp_poller import poll_all_nodes
from ml_engine.inference import MLInferenceService
from self_healing.routing_controller import RoutingController
from self_healing.alert_reconciler import AlertReconciler

logger = logging.getLogger("bridge_server")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

app = FastAPI(title="Autonomous Self-Healing Network Bridge Server")

# ── CORS (React dev server on :5173 needs this) ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Simulation state (module-level singletons) ──
graph = build_topology(n_nodes=10, seed=42)
injector = FaultInjector(graph)
traffic_sim = TrafficSimulator(graph)
controller = RoutingController(graph)
reconciler = AlertReconciler(auto_subscribe=True)

# Start ML inference service — subscribes to TOPIC_TELEMETRY, publishes TOPIC_ALERT on anomalies
_ml_service = MLInferenceService(auto_subscribe=True)

initial_route = ["A", "B", "C", "D", "E"]
controller.set_active_path("A", "E", initial_route)

connected_clients: List[WebSocket] = []

# The asyncio event loop used by uvicorn — captured on startup
_event_loop: asyncio.AbstractEventLoop | None = None


class FaultRequest(BaseModel):
    kind: str
    target: Any


# ── Event bus → WebSocket broadcast ──────────────────────────────────────────
# The event bus callbacks can be called from ANY thread (polling thread, etc.).
# asyncio.create_task() is NOT thread-safe; use loop.call_soon_threadsafe instead.

def _make_message(msg_type: str, payload_obj: Any) -> str:
    payload_dict = (
        asdict(payload_obj)
        if hasattr(payload_obj, "__dataclass_fields__")
        else (payload_obj if isinstance(payload_obj, dict) else {"data": str(payload_obj)})
    )
    return json.dumps({"type": msg_type, "payload": payload_dict})


def _schedule_broadcast(msg_type: str, payload_obj: Any) -> None:
    """Thread-safe: schedules a WebSocket broadcast onto the uvicorn event loop."""
    if not connected_clients or _event_loop is None:
        return
    message = _make_message(msg_type, payload_obj)

    async def _send_all():
        dead = []
        for client in list(connected_clients):
            try:
                await client.send_text(message)
            except Exception:
                dead.append(client)
        for d in dead:
            if d in connected_clients:
                connected_clients.remove(d)

    asyncio.run_coroutine_threadsafe(_send_all(), _event_loop)


bus.subscribe(TOPIC_TELEMETRY, lambda p: _schedule_broadcast("telemetry.reading", p))
bus.subscribe(TOPIC_ALERT,     lambda p: _schedule_broadcast("alert.raised", p))
bus.subscribe(TOPIC_REROUTE,   lambda p: _schedule_broadcast("reroute.completed", p))


# ── Periodic SNMP polling loop (background thread) ───────────────────────────
_stop_polling = threading.Event()


def _polling_loop():
    """
    Background daemon thread: polls all node telemetry every POLL_INTERVAL_SEC seconds.
    Each call to poll_all_nodes() publishes TelemetryReading events on the bus →
    MLInferenceService receives them → raises Alert if abnormal → RoutingController heals.
    """
    logger.info(f"SNMP polling loop started (interval={POLL_INTERVAL_SEC}s)")
    while not _stop_polling.is_set():
        try:
            t = time.time()
            poll_all_nodes(graph, timestamp=t)
        except Exception as e:
            logger.error(f"Polling error: {e}")
        _stop_polling.wait(POLL_INTERVAL_SEC)
    logger.info("SNMP polling loop stopped.")


# ── FastAPI lifecycle ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    global _event_loop
    _event_loop = asyncio.get_running_loop()

    # Start background polling thread
    _poll_thread = threading.Thread(target=_polling_loop, daemon=True, name="snmp-poller")
    _poll_thread.start()
    logger.info("Bridge server started — polling loop and ML inference active.")


@app.on_event("shutdown")
async def shutdown_event():
    _stop_polling.set()
    logger.info("Bridge server shut down.")


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws/events")
async def websocket_events_endpoint(websocket: WebSocket):
    """WebSocket stream: relays telemetry, alerts, and reroute events in real time."""
    await websocket.accept()
    connected_clients.append(websocket)
    logger.info(f"WebSocket client connected. Total: {len(connected_clients)}")
    try:
        while True:
            # Keep the connection alive; we don't expect client → server messages
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total: {len(connected_clients)}")


# ── REST endpoints ────────────────────────────────────────────────────────────

@app.get("/api/topology")
def get_topology():
    """Return nodes and edges with current telemetry state."""
    nodes = [{"id": n, "status": graph.nodes[n].get("status", "up")} for n in sorted(graph.nodes())]
    edges = [
        {
            "source": u,
            "target": v,
            "link": f"{u}-{v}",
            "latency": data.get("latency", 5.0),
            "packet_loss": data.get("packet_loss", 0.0),
            "utilization": data.get("utilization", 0.2),
            "jitter": data.get("jitter", 1.0),
            "throughput": data.get("throughput", 100.0),
            "status": data.get("status", "healthy"),
            "ifOperStatus": data.get("ifOperStatus", 1),
        }
        for u, v, data in graph.edges(data=True)
    ]
    active_paths = {f"{k[0]}->{k[1]}": v for k, v in controller.active_paths.items()}
    return {"nodes": nodes, "edges": edges, "active_paths": active_paths}


@app.post("/api/fault")
def inject_fault_endpoint(req: FaultRequest):
    """Inject a network fault (calls Member 1's FaultInjector)."""
    payload = injector.inject(kind=req.kind, target=req.target)
    return {"status": "ok", "fault": payload}


@app.post("/api/reset")
def reset_network_endpoint():
    """Reset network to healthy state."""
    injector.reset_faults()
    controller.set_active_path("A", "E", ["A", "B", "C", "D", "E"])
    _ml_service.reset_state()
    return {"status": "ok", "message": "Network restored to healthy state."}


@app.get("/api/feature-importance")
def get_feature_importance_endpoint():
    """Serve Member 2's saved feature importance HTML chart."""
    html_file = MODELS_DIR / "feature_importance.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    return JSONResponse(content={"message": "Feature importance not generated yet. Run: python -m ml_engine.train_pipeline"}, status_code=404)


@app.get("/api/reconciliation")
def get_reconciliation_endpoint():
    """Return TRAP vs ML reconciliation records from events.jsonl."""
    records = []
    if EVENTS_LOG_FILE.exists():
        with open(EVENTS_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        entry = json.loads(line)
                        if entry.get("type") == "reconciliation":
                            records.append(entry.get("payload"))
                    except json.JSONDecodeError:
                        pass
    return {"records": records, "summary": reconciler.get_summary_stats()}


# ── Serve Vite production build (frontend/dist) ───────────────────────────────
# In dev mode: Vite dev server (npm run dev) handles frontend; proxy sends /api/* and /ws/* here.
# In prod mode: uvicorn serves the built dist/ bundle.
_DIST = PROJECT_ROOT / "frontend" / "dist"
if _DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
    def serve_spa(full_path: str):
        # Don't intercept API or WS routes
        if full_path.startswith(("api/", "ws/")):
            return JSONResponse({"error": "not found"}, status_code=404)
        index = _DIST / "index.html"
        if index.exists():
            return index.read_text(encoding="utf-8")
        return "<h1>Run: cd frontend && npm run build</h1>"
