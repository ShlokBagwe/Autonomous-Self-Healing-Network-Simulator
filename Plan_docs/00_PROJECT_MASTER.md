# Autonomous Self-Healing Network Simulator — Master Technical Plan

**Version:** Revision 2 (SNMP + Random Forest Feature Importance)
**Team size:** 4
**Timeline:** 4 weeks
**Platform:** Python 3.10+, Windows/macOS/Linux
**Purpose of this file:** single source of truth for the whole project. Each teammate's coding agent should read this file first, then their own `member-N-*.md` file. This file defines the shared contracts (interfaces, data schemas, file layout, integration points) that make 4 independently-built pieces merge into one working system without conflict.

---

## 1. Project Definition

**Problem.** Traditional/static routing keeps using a poor path even when a link is delayed, congested, or failing. Recovery often needs manual intervention.

**Solution.** A pure-software network simulator that:
1. Simulates a virtual network (8–12 nodes) carrying traffic.
2. Collects telemetry from every node via **SNMP** (GET/GETBULK polling + TRAP on fault).
3. Uses **ML** (Isolation Forest + Random Forest) to detect and classify network state (healthy / congested / failed).
4. Diagnoses the affected node/link.
5. Dynamically recalculates the shortest/best path and reroutes traffic (self-healing controller).
6. Visualizes the entire loop on a dashboard.
7. Evaluates itself against a static-routing baseline using MTTD, MTTR, PDR, latency, throughput recovery, and SNMP TRAP latency.

**Scope boundary (do not violate):**
- No physical routers, VMs, cloud infra, or real telecom hardware.
- No OSPF/BGP/SDN required — routing logic is NetworkX + Dijkstra only.
- SNMP is a **monitoring/management protocol only**, run entirely over `localhost` UDP between simulated agents. It does not count as "real routing infrastructure" and does not violate the scope boundary.

---

## 2. System Architecture (Core Loop)

```
USER / ADMIN
   |
   v
[Frontend / Dashboard]  (Member 4)
   | fault injection + live view
   v
[Virtual Network Simulator]  (Member 1)
   |
   v
[SNMP Agents on Simulated Nodes]  (Member 1)
   |
   v
[Telemetry Monitor]  (Member 1 -> feeds Member 2)
   | SNMP GET/GETBULK polling + SNMP TRAP on fault
   | features: RTT, jitter, packet_loss, queue, throughput, utilization
   v
[ML Detection / Classification]  (Member 2)
   |
   v
[Diagnosis]  (Member 3)
   |
   v
[Self-Healing Controller]  (Member 3)
   | dynamic edge cost + path recalculation + TRAP/ML reconciliation
   v
[Traffic Rerouting]  (Member 3)
   |
   v
[Recovery + Evaluation Logs]  (Member 4)
```

**Core loop:** Simulate → Monitor (SNMP) → Detect (ML) → Diagnose → Reroute → Verify → Measure

---

## 3. Repository Layout (shared — do not deviate)

This exact structure is what lets 4 independently-developed pieces merge cleanly. Each member works almost entirely inside their own top-level folder and touches `shared/` only through the interfaces defined in Section 5.

```
self-healing-network/
├── README.md
├── requirements.txt
├── shared/
│   ├── __init__.py
│   ├── schemas.py          # dataclasses / typed dicts used by ALL modules (Section 5)
│   ├── config.py           # shared constants: node count, poll interval, OIDs, ports
│   └── event_bus.py        # simple pub/sub so modules don't import each other directly
├── network_sim/            # Member 1
│   ├── topology.py
│   ├── traffic.py
│   ├── fault_injector.py
│   └── snmp_agent.py
├── telemetry/               # Member 1
│   ├── snmp_poller.py
│   └── trap_listener.py
├── ml_engine/               # Member 2
│   ├── dataset_gen.py
│   ├── isolation_forest.py
│   ├── random_forest.py
│   └── feature_importance.py
├── self_healing/            # Member 3
│   ├── diagnosis.py
│   ├── routing_controller.py
│   └── alert_reconciler.py
├── frontend/                # Member 4
│   ├──             # using tailwind CSS and React or any better UI
│   └── components/
├── evaluation/               # Member 4
│   ├── benchmark_runner.py
│   ├── metrics.py
│   └── report_figures.py
├── data/
│   ├── raw/                 # generated telemetry CSVs
│   └── models/              # saved .pkl models
└── logs/
    └── events.jsonl         # unified event log (all modules append here)
```

**Rule:** nobody imports another member's internal module directly. Everyone imports from `shared/schemas.py` and communicates via `shared/event_bus.py` or `logs/events.jsonl`. This is what makes 4 parallel work-streams mergeable — no one is blocked waiting for someone else's code to exist, because they code against the schema, not the implementation.

---

## 4. Data & Telemetry Design

### 4.1 Telemetry features (per node, per timestamp)

| Feature | Meaning | Unit |
|---|---|---|
| `timestamp` | simulation time | float (seconds) |
| `node_id` / `link` | which element | string, e.g. `"A"` or `"A-B"` |
| `latency` | round-trip delay | ms |
| `jitter` | variation in delay | ms |
| `packet_loss` | % dropped packets | 0–100 |
| `queue_size` | queued packets | int |
| `throughput` | successfully transmitted traffic | Mbps |
| `bandwidth_utilization` | used vs available bandwidth | 0–1 |
| `state` | ground-truth label | `healthy` \| `congested` \| `failed` |

CSV header (canonical — used by dataset generation, ML training, and evaluation):
```
timestamp,link,latency,jitter,packet_loss,queue,throughput,utilization,state
```

### 4.2 SNMP OID map (shared/config.py `OID_MAP`)

| OID (custom base `1.3.6.1.4.1.9999.1.x`) | Meaning | Standard equivalent |
|---|---|---|
| `.1` | latency (ms) | custom |
| `.2` | jitter (ms) | custom |
| `.3` | packet_loss (%) | custom |
| `.4` | queue_size | custom |
| `.5` | throughput | custom |
| `.6` | bandwidth_utilization | custom |
| `.7` | ifOperStatus | MIB-II standard (1=up, 2=down) |
| `.8` | ifInErrors | MIB-II standard |

Poll interval: **1.0 second** (fixed constant in `shared/config.py: POLL_INTERVAL_SEC = 1.0`). This is the floor on MTTD — do not report MTTD figures below this without noting it.

---

## 5. Shared Interfaces (the contract everyone codes against)

These live in `shared/schemas.py` and must be implemented **exactly as specified** — this is what lets 4 people build independently and merge without a integration-week rewrite.

```python
# shared/schemas.py
from dataclasses import dataclass
from typing import Literal, Optional

State = Literal["healthy", "congested", "failed"]

@dataclass
class TelemetryReading:
    timestamp: float
    link: str            # e.g. "A-B"
    latency: float
    jitter: float
    packet_loss: float
    queue: float
    throughput: float
    utilization: float
    state: Optional[State] = None   # ground truth, only present in training data

@dataclass
class Alert:
    timestamp: float
    source: Literal["snmp_trap", "ml_engine"]
    link: str
    predicted_state: State
    confidence: Optional[float] = None   # ML only; None for TRAP

@dataclass
class RerouteEvent:
    timestamp: float
    failed_link: str
    old_path: list[str]
    new_path: list[str]
    trigger_alert: Alert
    recovery_latency_ms: Optional[float] = None
```

```python
# shared/event_bus.py — minimal pub/sub, no external dependency
class EventBus:
    def __init__(self): self._subs = {}
    def subscribe(self, topic: str, callback): self._subs.setdefault(topic, []).append(callback)
    def publish(self, topic: str, payload): 
        for cb in self._subs.get(topic, []): cb(payload)

bus = EventBus()
```

**Topics everyone publishes/subscribes to:**
- `"telemetry.reading"` — Member 1 publishes `TelemetryReading` every poll (Member 2 subscribes for live inference; Member 4 subscribes for dashboard charts).
- `"alert.raised"` — Member 2 (ML) and Member 1 (SNMP TRAP listener) both publish `Alert` objects here. Member 3 subscribes to both sources.
- `"reroute.completed"` — Member 3 publishes `RerouteEvent` after healing. Member 4 subscribes for logs/dashboard, evaluation subscribes for metrics.

**Unified log file** (`logs/events.jsonl`): every `Alert` and `RerouteEvent` is also appended here as one JSON object per line, with a `type` field. This is the file Member 4's evaluation scripts read — nobody should build a separate logging mechanism.

---

## 6. Module Specs (what each piece must expose)

### 6.1 `network_sim/topology.py` (Member 1)
- `build_topology(n_nodes=10) -> networkx.Graph` — random or fixed 8–12 node graph with weighted edges (base_cost).
- Edge weight formula (used everywhere downstream): `cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty`

### 6.2 `network_sim/fault_injector.py` (Member 1)
- `inject_fault(graph, kind: Literal["link_failure","router_crash","congestion","degradation","multi_fault"], target) -> None`
- Must call `snmp_agent.fire_trap(target)` at the moment of injection (this is the TRAP alert path).

### 6.3 `network_sim/snmp_agent.py` + `telemetry/snmp_poller.py` (Member 1)
- Each node runs a `pysnmp` agent on `localhost:<161xx>` exposing the OID map (Section 4.2).
- `snmp_poller.py`: `poll_all_nodes() -> list[TelemetryReading]`, called every `POLL_INTERVAL_SEC`, publishes to `"telemetry.reading"`.
- `telemetry/trap_listener.py`: listens for TRAPs, publishes `Alert(source="snmp_trap", ...)` to `"alert.raised"`.

### 6.4 `ml_engine/` (Member 2)
- `dataset_gen.py`: `generate_dataset(n_samples) -> pandas.DataFrame` matching the CSV schema in 4.1. Must include EDA outputs (class balance, feature distributions) saved to `data/raw/`.
- `isolation_forest.py`: `train_iforest(df) -> sklearn model`, unsupervised anomaly flag.
- `random_forest.py`: `train_rf(df) -> sklearn model`, classifies `state`. Save to `data/models/rf.pkl`.
- `feature_importance.py`: `get_feature_importance(model, feature_names) -> pandas.Series`, plus a Plotly bar chart saved as `data/models/feature_importance.html`. **This is the mandatory explainability deliverable — do not skip.**
- Live inference: subscribes to `"telemetry.reading"`, runs the trained RF model, publishes `Alert(source="ml_engine", confidence=...)` to `"alert.raised"` whenever predicted state != "healthy".

### 6.5 `self_healing/` (Member 3)
- `alert_reconciler.py`: subscribes to `"alert.raised"`. Logs every alert with its source. If both TRAP and ML fire for the same link within a time window, record `agreement=True`; if only one fires, record which. This produces the TRAP-vs-ML comparison data for Section 9's evaluation metric.
- `diagnosis.py`: `diagnose(alert: Alert, graph) -> (affected_element, severity)`.
- `routing_controller.py`: `recalculate_route(graph, source, dest, failed_element) -> list[str]` using NetworkX Dijkstra with the dynamic edge-cost formula (6.1). Publishes `RerouteEvent` to `"reroute.completed"`.

### 6.6 `frontend/` (Member 4)
- using tailwind CSS and React or any better UI
- Subscribes to `"telemetry.reading"`, `"alert.raised"`, `"reroute.completed"` and renders: live topology, latency/loss/queue/jitter charts, fault-injection buttons (calls `fault_injector.inject_fault`), alert feed (source-tagged TRAP vs ML), rerouted-path highlight, feature-importance chart from Member 2's saved HTML.

### 6.7 `evaluation/` (Member 4)
- `benchmark_runner.py`: runs each fault scenario N times (recommend N≥10) under (a) static routing baseline, (b) self-healing system. Vary random seed per run.
- `metrics.py`: computes MTTD, MTTR, PDR, avg latency, throughput recovery time, SNMP TRAP latency vs MTTD, and RF accuracy/precision/recall/F1. Reports **mean ± std** and a significance test (Mann-Whitney U, `scipy.stats.mannwhitneyu`) between static vs self-healing for each metric.
- `report_figures.py`: generates the final comparison charts for the report/demo.

## 6.8 Frontend Bridge Layer (React + Tailwind CSS)

The frontend is React + Tailwind CSS, not a Python-native dashboard (Streamlit/Dash). Since React cannot import `shared/event_bus.py` directly, Member 4 must run a lightweight bridge server that relays event bus topics to the browser over HTTP/WebSocket. This bridge is itself a shared contract — do not change its message shapes without updating this section first.

**Bridge server:** `frontend/bridge_server.py` (FastAPI recommended — small, async-native, pairs well with WebSocket)

- Subscribes to the same three bus topics as before: `"telemetry.reading"`, `"alert.raised"`, `"reroute.completed"`.
- Re-publishes each one to a WebSocket endpoint the React app connects to, e.g. `ws://localhost:8000/ws/events`.
- Every message sent over the WebSocket is a JSON object with a `type` field matching the event topic, and a `payload` field matching the corresponding shared dataclass (Section 5), serialized via `dataclasses.asdict()`:

```json
{ "type": "telemetry.reading", "payload": { "timestamp": 12.5, "link": "A-B", "latency": 42.1, "jitter": 3.2, "packet_loss": 0.5, "queue": 4, "throughput": 88.2, "utilization": 0.6, "state": null } }
{ "type": "alert.raised", "payload": { "timestamp": 13.0, "source": "snmp_trap", "link": "B-C", "predicted_state": "failed", "confidence": null } }
{ "type": "reroute.completed", "payload": { "timestamp": 13.4, "failed_link": "B-C", "old_path": ["A","B","C"], "new_path": ["A","D","C"], "trigger_alert": {...}, "recovery_latency_ms": 400 } }
```

**REST endpoints** (for one-off actions, not streamed):
- `POST /api/fault` — body `{ "kind": "link_failure", "target": "B-C" }` → calls Member 1's `fault_injector.inject_fault()`. This is what the React fault-injection buttons call.
- `GET /api/feature-importance` — returns Member 2's saved `data/models/feature_importance.html` (or its underlying data as JSON, if the React app renders its own chart instead of embedding the HTML).
- `GET /api/reconciliation` — reads `logs/events.jsonl` and returns Member 3's TRAP/ML reconciliation records, for the dashboard's alert feed and Member 4's evaluation figures.

**Rule:** the bridge only relays and exposes — it must not contain any diagnosis, routing, or ML logic itself. All decision-making stays in `self_healing/` and `ml_engine/`; the bridge is a pure transport layer, same as the event bus it sits on top of.

---

## 7. Fault Scenarios (must all be demonstrable)

| Scenario | Injected condition | Expected system action |
|---|---|---|
| Link failure | B–C unavailable | TRAP + ML detect → reroute |
| Router crash | node stops forwarding | TRAP (agent unreachable) → bypass node |
| Severe congestion | latency/queue/loss spike | SNMP polling shows degraded OIDs → reroute |
| Progressive degradation | gradual jitter/queue/loss worsening | early warning before full failure (advanced) |
| Multiple faults | 2+ simultaneous | best surviving path found (advanced) |

---

## 8. Evaluation Metrics (Definition of Done for Member 4, but everyone should know these)

| Metric | Formula / method | Expected direction |
|---|---|---|
| MTTD | `t_detected - t_fault_onset` (from ML or TRAP, whichever first) | lower better |
| MTTR | `t_recovered - t_fault_onset` | lower better |
| SNMP TRAP latency | `t_trap_received - t_fault_onset`; compare distribution to MTTD | reactive vs proactive comparison |
| PDR | successful_packets / total_packets | higher better |
| Avg latency | mean RTT before/during/after fault | lower/faster recovery better |
| Throughput recovery | time for throughput to return to baseline | faster better |
| ML Accuracy/Precision/Recall/F1 | standard sklearn `classification_report` | higher, balanced with false-alarm rate |

**Do not report a single-run number as a result.** Every headline metric must be mean ± std across ≥10 runs with a significance test, per Section 6.7.

---

## 9. Four-Week Plan (shared checkpoints — everyone syncs at these)

| Week | Goal | Cross-team checkpoint |
|---|---|---|
| 1 | Network foundation. Member 1 builds topology + traffic + fault injector with telemetry **behind the `TelemetryReading` interface** (in-process is fine, but must match the schema exactly — this is what makes Week 2's SNMP swap a drop-in, not a rewrite). | End of week: everyone can import `shared/schemas.py` and `shared/event_bus.py` and see fake/real telemetry flowing. |
| 2 | Member 1 swaps telemetry to real SNMP (GET/GETBULK + TRAP). Member 2 generates dataset, trains IF/RF, ships feature importance. Member 3 builds diagnosis + routing controller against the `Alert`/`RerouteEvent` schema (can use Member 2's dummy alerts until real ones exist). | Mid-week: confirm SNMP poll interval didn't break the `TelemetryReading` schema. End of week: full detect→reroute loop works end to end on at least one fault type. |
| 3 | Member 4 builds frontend + integrates all event bus topics. Everyone fixes integration bugs found here — this is why the schema-first approach in Section 5 matters. | All 5 fault scenarios demonstrable through the UI. |
| 4 | Member 4 runs the static-vs-self-healing benchmark (≥10 runs/scenario), generates report figures. Everyone polishes their module and reviews the final report together. | Definition of Done checklist (Section 10) fully checked. |

---

## 10. Definition of Done

- [ ] 8–12 node topology simulated with packet flow
- [ ] Fault injector covers all 5 scenario types
- [ ] SNMP agents running per node; poller collects via GET/GETBULK
- [ ] SNMP TRAP fires on fault injection
- [ ] Telemetry dataset generated with EDA
- [ ] Isolation Forest + Random Forest trained and evaluated
- [ ] Random Forest feature importance extracted and charted
- [ ] Diagnosis + dynamic routing controller working
- [ ] TRAP vs ML alert reconciliation logged
- [ ] Frontend shows topology, live metrics, alerts (source-tagged), rerouted path, feature importance
- [ ] Static vs self-healing benchmark run ≥10x per scenario with mean±std and significance test
- [ ] Final report + demo + PPT assembled from `evaluation/report_figures.py` output

---

## 11. Work Division Summary (full detail in each member's own file)

| Member | Owns | File |
|---|---|---|
| 1 | Network simulation, fault injector, SNMP agents & polling | `member-1-network-sim.md` |
| 2 | Telemetry dataset, ML models, feature importance | `member-2-ml-engine.md` |
| 3 | Diagnosis, self-healing controller, TRAP/ML reconciliation | `member-3-self-healing.md` |
| 4 | Frontend, evaluation, benchmarking, report | `member-4-frontend-eval.md` |

---

## 12. Notes for the Implementing Agent

- Treat Section 5 (Shared Interfaces) as immutable once Week 1 ends. If a change is genuinely needed, it must be proposed and updated in **this file first**, then propagated — never diverge silently in one member's branch.
- Everyone reads/writes telemetry and alerts through `shared/event_bus.py` and `logs/events.jsonl`, never by importing another member's module directly. This is what allows 4 branches to merge with minimal conflict.
- Git convention: one branch per member (`member-1`, `member-2`, `member-3`, `member-4`), merge to `main` at each weekly checkpoint, not continuously — this matches the weekly sync points in Section 9.
- When in doubt about scope, re-check Section 1's boundary: no physical hardware, no OSPF/BGP/SDN requirement, SNMP stays localhost-only.
