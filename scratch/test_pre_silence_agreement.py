import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import networkx as nx

from shared.event_bus import bus
from shared.config import TOPIC_ALERT, TOPIC_FAULT, TOPIC_TELEMETRY, TOPIC_REROUTE
from shared.schemas import Alert, TelemetryReading, RerouteEvent
from network_sim.topology import build_topology
from network_sim.fault_injector import FaultInjector, _resolve_link_nodes
from network_sim.snmp_agent import agent_manager
from ml_engine.inference import MLInferenceService
from self_healing.alert_reconciler import AlertReconciler
from self_healing.routing_controller import RoutingController
from telemetry.snmp_poller import poll_all_nodes
from evaluation.metrics import compute_avg_rtt_latency, compute_split_mttr

# Clean bus
bus.clear()

g = build_topology(n_nodes=10, seed=42)
agent_manager.init_agents(g)
agent_manager.sync_telemetry(g)

reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=True)
ml_service = MLInferenceService(auto_subscribe=True)
controller = RoutingController(g)

# Track events
all_alerts = []
all_reroutes = []
all_telemetry = []

bus.subscribe(TOPIC_ALERT, lambda a: all_alerts.append(a))
bus.subscribe(TOPIC_REROUTE, lambda r: all_reroutes.append(r))
bus.subscribe(TOPIC_TELEMETRY, lambda t: all_telemetry.append(t))

controller.set_active_path("A", "E", ["A", "B", "C", "D", "E"])

print(f"Initial active path A->E: {controller.active_paths[('A', 'E')]}")

# Inject link_failure with final reading logic
t_now = time.time()

# Perform link_failure manually simulating the proposed injector logic:
link_str = "D-E"
u, v = "D", "E"
base_lat = float(g.edges[u, v].get("base_latency", g.edges[u, v].get("latency", 8.0)))

g.edges[u, v].update({
    "failure_risk": 1.0,
    "packet_loss": 100.0,
    "throughput": 0.0,
    "ifOperStatus": 2,
    "status": "failed",
})

# 1. Fire TRAP
trap_alert = agent_manager.fire_trap(link_str, timestamp=t_now)

# 2. Emit one final pre-silence TelemetryReading
final_reading = TelemetryReading(
    timestamp=round(t_now, 3),
    link=f"{min(u, v)}-{max(u, v)}",
    latency=round(base_lat + 342.0, 2),
    jitter=45.0,
    packet_loss=100.0,
    queue=0.0,
    throughput=0.0,
    utilization=0.0,
    state="failed",
)
bus.publish(TOPIC_TELEMETRY, final_reading)

# 3. Check results
print("\n--- Alerts Published ---")
for a in all_alerts:
    print(f"Source: {a.source}, Link: {a.link}, State: {a.predicted_state}, Conf: {a.confidence}, Ts: {a.timestamp}")

print("\n--- Reconciliation Records ---")
for r in reconciler.reconciliation_history:
    print(f"Link: {r.link}, Agreement: {r.agreement}, Sources: {r.sources}, Delta: {r.time_delta_sec}s, State: {r.predicted_state}")

print("\n--- Summary Stats ---")
stats = reconciler.get_summary_stats()
print(stats)

print("\n--- Reroute Events ---")
for re in all_reroutes:
    print(f"Failed Link: {re.failed_link}, Old Path: {re.old_path}, New Path: {re.new_path}, Trigger: {re.trigger_alert.source}, MTTR: {re.recovery_latency_ms}ms")

print(f"\nTotal reroutes triggered: {len(all_reroutes)}")

split_mttr = compute_split_mttr(all_reroutes)
print(f"Split MTTR: {split_mttr}")

# Verify subsequent poll excludes D-E
readings = poll_all_nodes(g, timestamp=t_now + 1.0)
print(f"\nSubsequent poll reading count: {len(readings)} (Expected 16)")
assert len(readings) == 16
assert not any(r.link in ("D-E", "E-D") for r in readings)
avg_lat = compute_avg_rtt_latency(readings)
print(f"Avg RTT Latency: {avg_lat} ms")

print("\n================== ROUTER CRASH TEST ==================")
# Reset topology
injector = FaultInjector(g)
injector.reset_faults()
reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=True)
ml_service.reset_state()

node_crash = "C"
incident_edges = [(node_crash, nbr) for nbr in sorted(list(g.neighbors(node_crash)))]
print(f"Crashing router {node_crash} with incident edges: {incident_edges}")

crash_telemetry = []
bus.subscribe(TOPIC_TELEMETRY, lambda t: crash_telemetry.append(t))

t_crash = time.time()
g.nodes[node_crash]["status"] = "down"
for u_n, v_n in incident_edges:
    g.edges[u_n, v_n].update({
        "failure_risk": 1.0,
        "packet_loss": 100.0,
        "throughput": 0.0,
        "ifOperStatus": 2,
        "status": "failed",
    })

agent_manager.fire_trap(node_crash, timestamp=t_crash)

# Emit final pre-silence reading for each incident edge
for u_n, v_n in incident_edges:
    base_lat = float(g.edges[u_n, v_n].get("base_latency", g.edges[u_n, v_n].get("latency", 8.0)))
    canon_link = f"{min(u_n, v_n)}-{max(u_n, v_n)}"
    final_reading = TelemetryReading(
        timestamp=round(t_crash, 3),
        link=canon_link,
        latency=round(base_lat + 342.0, 2),
        jitter=45.0,
        packet_loss=100.0,
        queue=0.0,
        throughput=0.0,
        utilization=0.0,
        state="failed",
    )
    bus.publish(TOPIC_TELEMETRY, final_reading)

print(f"Final readings emitted for router crash: {len(crash_telemetry)}")
for r in crash_telemetry:
    print(f"  Final reading: link={r.link}, lat={r.latency}, loss={r.packet_loss}, status={r.state}")

readings_after_crash = poll_all_nodes(g, timestamp=t_crash + 1.0)
print(f"Readings after crash: {len(readings_after_crash)} (Expected 15)")
assert len(readings_after_crash) == 17 - len(incident_edges)
assert not any(node_crash in r.link.split("-") for r in readings_after_crash)
print("Router crash verification SUCCESS!")

