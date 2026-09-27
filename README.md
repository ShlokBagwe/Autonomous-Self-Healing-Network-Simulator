# Autonomous Self-Healing Network Simulator

An end-to-end, pure-software autonomous network simulator featuring virtual telemetry, machine learning anomaly detection and classification, explainable AI, proactive/reactive fault diagnosis, dynamic Dijkstra rerouting, and real-time reconciliation of reactive SNMP TRAP vs. proactive ML alerts.

---

## 🏗️ System Architecture & Core Loop

```
Simulate (M1) ➔ Monitor/SNMP (M1) ➔ Detect/ML (M2) ➔ Diagnose (M3) ➔ Reroute (M3) ➔ Measure & Visualize (M4)
```

The system operates across 4 modular, decoupled components communicating via a shared in-process `EventBus` (`shared/event_bus.py`) and a unified log file (`logs/events.jsonl`):

```
self-healing-network/
├── README.md                   # Complete system documentation with per-member sections
├── Project_Explanation.md      # Detailed, plain-English conceptual walkthrough & UI guide
├── requirements.txt            # Unified dependencies
├── run.ps1 / run.bat           # Automated single-command stack launchers
├── shared/                     # Shared immutable interfaces (Section 5)
│   ├── schemas.py              # TelemetryReading, Alert, RerouteEvent, ReconciliationRecord
│   ├── config.py               # Constants, OIDs, penalty weights, topics, paths
│   └── event_bus.py            # Thread-safe pub/sub event bus
├── network_sim/                # Member 1: Network simulation, topology & faults
│   ├── topology.py             # 8-12 node graph generation with seed & dynamic edge costs
│   ├── traffic.py              # Packet flow simulation & PDR tracking
│   ├── fault_injector.py       # 5 fault scenarios & reactive TRAP triggers
│   └── snmp_agent.py           # Per-node SNMP agents exposing enterprise OID map
├── telemetry/                  # Member 1: Telemetry collection
│   ├── snmp_poller.py          # GET/GETBULK polling publishing TelemetryReading
│   └── trap_listener.py        # Immediate TRAP listener publishing Alert
├── ml_engine/                  # Member 2: Machine Learning Engine
│   ├── dataset_gen.py          # Synthetic dataset generation & automated EDA
│   ├── isolation_forest.py     # Unsupervised anomaly detection
│   ├── random_forest.py        # Supervised 3-class classifier with confidence
│   ├── feature_importance.py   # Explainable AI rankings & interactive HTML chart
│   ├── inference.py            # Real-time inference subscriber
│   └── train_pipeline.py       # End-to-end training and artifact generation
├── self_healing/               # Member 3: Decision & Self-Healing
│   ├── diagnosis.py            # Fault mapping & severity computation
│   ├── routing_controller.py   # Dynamic Dijkstra recalculation & MTTR tracking
│   ├── alert_reconciler.py     # Reactive TRAP vs Proactive ML alert reconciliation
│   └── demo_simulation.py      # Standalone verification harness
├── frontend/                   # Member 4: React + Vite + Tailwind dashboard
│   ├── bridge_server.py        # FastAPI async bridge – WebSocket /ws/events + REST
│   ├── vite.config.js          # Vite 8 + Tailwind CSS v4 + dev proxy to :8000
│   ├── index.html              # Vite HTML shell (mounts React)
│   └── src/
│       ├── App.jsx             # Root layout (topology + panels + sidebar)
│       ├── main.jsx            # React root with ErrorBoundary wrapper
│       ├── api/client.js       # REST fetch wrappers + reconnecting WebSocket
│       ├── hooks/useEventStream.js  # WS hook – alerts, reroutes, telemetry Map
│       └── components/
│           ├── ErrorBoundary.jsx    # Crash-prevention boundary with reload modal
│           ├── TopologyGraph.jsx    # Dynamic SVG – all nodes from /api/topology + WS latency
│           ├── FaultInjector.jsx    # Target+kind from live topology; multi-select
│           ├── MetricsPanel.jsx     # RTT, PDR, TRAP/ML agreement, MTTR, util, jitter
│           ├── AlertFeed.jsx        # Source-tagged (TRAP vs ML) live feed
│           ├── RerouteLog.jsx       # Old→New path + MTTR per reroute event
│           └── FeatureImportance.jsx # Embedded /api/feature-importance iframe
├── evaluation/                 # Member 4: Statistical Benchmarking
│   ├── metrics.py              # MTTD, MTTR, PDR, Mann-Whitney U test
│   ├── benchmark_runner.py     # N>=10 runs across 5 scenarios with varied seeds
│   └── report_figures.py       # Comparison summary generator & HTML evaluation report
├── data/
│   ├── raw/                    # Telemetry dataset & EDA summary
│   └── models/                 # Saved rf.pkl model & feature_importance.html
└── logs/
    ├── events.jsonl            # Unified log for alerts, reroutes & reconciliations
    ├── benchmark_results.json  # Benchmark output data across 5 scenarios
    └── evaluation_report.html  # Generated benchmark report
```

---

## 🧩 Shared Foundation (`shared/`)

- **Schemas (`shared/schemas.py`)**:
  - `TelemetryReading`: Canonical per-node telemetry record.
  - `Alert`: Trigger from `"snmp_trap"` or `"ml_engine"`.
  - `RerouteEvent`: Detailed log of path modification, trigger, and `recovery_latency_ms`.
  - `ReconciliationRecord`: TRAP vs. ML alignment, timestamps, time delta, and agreement status.
- **Configuration (`shared/config.py`)**:
  - `POLL_INTERVAL_SEC = 1.0s` (Floor on polling MTTD).
  - `RECONCILE_WINDOW_SEC = 2.0s`.
  - Base OID map: `1.3.6.1.4.1.9999.1.x` (latency, jitter, packet loss, queue, throughput, utilization, ifOperStatus, ifInErrors).
  - Dynamic edge cost weights: `cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty`.
- **Event Bus (`shared/event_bus.py`)**:
  - Thread-safe, decoupled pub/sub engine with canonical topics: `"telemetry.reading"`, `"alert.raised"`, `"reroute.completed"`, `"fault.injected"`.

---

## 📡 Member 1: Network Simulation & Telemetry

**Files:** `network_sim/topology.py`, `network_sim/traffic.py`, `network_sim/fault_injector.py`, `network_sim/snmp_agent.py`, `telemetry/snmp_poller.py`, `telemetry/trap_listener.py`

### Key Implementations:
1. **Virtual Topology (`network_sim/topology.py`)**:
   - `build_topology(n_nodes=10, seed=None)`: Builds connected 8–12 node networks with backbone rings and chordal cross-links.
   - Initialized with realistic latency (4–12 ms), jitter, zero loss, and dynamic cost weights. Accepts seeds for reproducible benchmarking.
2. **Traffic Simulation (`network_sim/traffic.py`)**:
   - `TrafficSimulator`: Drives discrete packet flows across active paths.
   - Evaluates delivery, path latency, and Packet Delivery Ratio (PDR = successful / total).
3. **Fault Injection (`network_sim/fault_injector.py`)**:
   - Implements all 5 required fault scenarios:
     - `link_failure`: Link down (`failure_risk=1.0`, `ifOperStatus=2`, 100% loss).
     - `router_crash`: Node down, all incident edges disabled.
     - `congestion`: Severe latency, queue spike (85), 12% loss, 96% utilization.
     - `degradation`: Progressive latency/jitter/queue worsening.
     - `multi_fault`: Multiple simultaneous link/node failures.
   - Records simulation timestamp `t_fault_onset` and publishes to `"fault.injected"`.
4. **SNMP Agents & Poller (`network_sim/snmp_agent.py`, `telemetry/snmp_poller.py`)**:
   - Simulates per-node agents with MIB tables mapped to custom enterprise OIDs (`1.3.6.1.4.1.9999.1.x`).
   - `poll_all_nodes()`: Collects readings every `POLL_INTERVAL_SEC` and publishes `TelemetryReading` to `"telemetry.reading"`.
   - `fire_trap()`: Immediately dispatches reactive SNMP TRAP on hard faults to `"alert.raised"`.

---

## 🧠 Member 2: Machine Learning Engine & Explainable AI

**Files:** `ml_engine/dataset_gen.py`, `ml_engine/isolation_forest.py`, `ml_engine/random_forest.py`, `ml_engine/feature_importance.py`, `ml_engine/inference.py`, `ml_engine/train_pipeline.py`

### Key Implementations:
1. **Synthetic Telemetry Dataset & EDA (`ml_engine/dataset_gen.py`)**:
   - Generates 6,000+ samples matching canonical CSV schema:
     `timestamp,link,latency,jitter,packet_loss,queue,throughput,utilization,state`
   - Generates distinct distributions for `healthy` (60%), `congested` (25%), and `failed` (15%).
   - Saves CSV and automated EDA summary (`data/raw/eda_summary.json`) containing class balance, feature means, and correlation matrices.
2. **Unsupervised Anomaly Detection (`ml_engine/isolation_forest.py`)**:
   - Trains `IsolationForest` on numeric features to provide an unsupervised early warning anomaly flag independent of class labels.
3. **Supervised State Classifier (`ml_engine/random_forest.py`)**:
   - Trains `RandomForestClassifier` (100 estimators, max depth 12).
   - Achieves **100% test accuracy** and **1.0 Macro F1** score on distinct fault profiles.
   - Serializes trained model to `data/models/rf.pkl`.
4. **Explainable AI (XAI) Deliverable (`ml_engine/feature_importance.py`)**:
   - Extracts normalized Gini feature importance:
     - **Latency**: 28.08%
     - **Throughput**: 26.02%
     - **Packet Loss**: 22.31%
     - **Jitter**: 12.36%
     - **Utilization**: 9.21%
     - **Queue Size**: 2.01%
   - Generates self-contained interactive visualization saved to `data/models/feature_importance.html`.
   - **Key Finding**: *Packet loss and latency dominate catastrophic failure detection; jitter and queue growth serve as the primary early-warning signatures for congestion and gradual degradation.*
5. **Real-time Inference Service (`ml_engine/inference.py`)**:
   - Subscribes to `"telemetry.reading"`, runs incoming readings through the RF model, and publishes `Alert(source="ml_engine", confidence=...)` to `"alert.raised"` whenever state != "healthy".

---

## 🛡️ Member 3: Decision & Self-Healing Controller

**Files:** `self_healing/diagnosis.py`, `self_healing/routing_controller.py`, `self_healing/alert_reconciler.py`, `self_healing/demo_simulation.py`

### Key Implementations:
1. **Fault Diagnosis (`self_healing/diagnosis.py`)**:
   - `diagnose(alert, graph)`: Unpacks to `(affected_element, severity)`.
   - Distinguishes link failures (`"A-B"`) from router crashes (`"C"`).
   - Severity engine: Assigns `1.0` (maximum severity) to reactive SNMP TRAPs; scales ML severity based on predicted state and classification confidence.
2. **Dynamic Dijkstra Routing Controller (`self_healing/routing_controller.py`)**:
   - Dynamic edge cost evaluation:
     $$\text{Cost} = \text{base\_cost} + (0.5 \cdot \text{latency}) + (10.0 \cdot \text{loss}) + (20.0 \cdot \text{congestion}) + (1000.0 \cdot \text{risk})$$
   - Uses **NetworkX Dijkstra** (`nx.dijkstra_path`) with dynamic penalties to recalculate routes around failed elements.
   - Tracks `recovery_latency_ms` relative to `t_fault_onset` for MTTR measurement.
   - Publishes `RerouteEvent` to `"reroute.completed"` and appends to `logs/events.jsonl`.
3. **TRAP vs. ML Alert Reconciliation (`self_healing/alert_reconciler.py`)**:
   - Evaluates reactive SNMP TRAP vs. proactive ML Engine alerts for the same link within `RECONCILE_WINDOW_SEC = 2.0s`.
   - Records `agreement = True` with time deltas and timestamps when both fire; automatically flushes solo alerts as `agreement = False`.
   - Appends records to `logs/events.jsonl` under `type: "reconciliation"`.

---

## 📊 Member 4: Frontend Dashboard & Statistical Evaluation

**Files:** `frontend/bridge_server.py`, `frontend/index.html`, `evaluation/metrics.py`, `evaluation/benchmark_runner.py`, `evaluation/report_figures.py`

### Key Implementations:
1. **Frontend Bridge Layer (`frontend/bridge_server.py`)**:
   - FastAPI server with WebSocket endpoint `/ws/events` relaying `"telemetry.reading"`, `"alert.raised"`, and `"reroute.completed"` live to the browser.
   - REST endpoints:
     - `POST /api/fault`: Injects any of the 5 fault scenarios.
     - `POST /api/reset`: Restores network to healthy state.
     - `GET /api/topology`: Returns nodes, links, and current active path.
     - `GET /api/feature-importance`: Serves explainable AI HTML chart.
     - `GET /api/reconciliation`: Serves TRAP/ML comparison records.
2. **Interactive UI Dashboard (`frontend/index.html`)**:
   - Glassmorphic dark-mode dashboard with interactive SVG topology map.
   - Dynamic path highlighting with glowing animation along active routes.
   - Live metrics (RTT, PDR, Agreement Rate, MTTR).
   - Fault injection panel for all 5 scenarios + network restore button.
   - Source-tagged Alert feed (SNMP TRAP vs ML Engine) and Reroute history.
   - Embedded explainable AI feature importance panel.
3. **Statistical Benchmarking Harness (`evaluation/benchmark_runner.py`)**:
   - Compares **Static Routing Baseline** vs. **Autonomous Self-Healing** across 10 runs per scenario (N=50 total runs) with varied seeds.
   - Computes Mean ± Std for MTTD, MTTR, PDR, and avg latency.
   - Executes Mann-Whitney U test (`scipy.stats.mannwhitneyu`) to prove statistical significance.
   - Results saved to `logs/benchmark_results.json`.
4. **Evaluation Report Figures (`evaluation/report_figures.py`)**:
   - Formats evaluation tables and generates visual comparison report (`logs/evaluation_report.html`).

---

## 📈 Benchmark Results Summary (N = 10 runs / scenario)

| Fault Scenario | Static Baseline PDR | Self-Healing PDR | Mean MTTD | Mean MTTR | Detection Mechanism |
|---|---|---|---|---|---|
| **Link Failure** | 92.5% ± 23.7% | **100.0% ± 0.0%** | 15.0 ms | 23.0 ms | Reactive TRAP + ML (Agreed) |
| **Router Crash** | 92.5% ± 23.7% | **100.0% ± 0.0%** | 15.0 ms | 23.0 ms | Reactive TRAP (Agent Unreachable) |
| **Severe Congestion** | 100.0% (degraded) | **100.0% (optimal)** | 120.0 ms | 128.0 ms | Proactive ML Engine |
| **Degradation** | 98.0% ± 4.8% | **100.0% ± 0.0%** | 120.0 ms | 128.0 ms | Proactive ML Engine |
| **Multi-Fault** | 92.5% ± 23.7% | **100.0% ± 0.0%** | 120.0 ms | 128.0 ms | Dual TRAP + Dynamic Dijkstra |

---

## 🚀 Setup & Execution Guide

### 1. Activate Virtual Environment
```powershell
# Windows
.\venv\Scripts\Activate.ps1
```

### 2. Run Comprehensive Unit & Integration Tests (16 Tests)
```bash
# Member 3 tests
pytest -v tests/test_member_3.py

# Full system tests (Members 1, 2, 3, 4)
pytest -v tests/test_full_system.py
```

### 3. Run ML Training & Feature Importance Pipeline
```bash
python -m ml_engine.train_pipeline
```

### 4. Run Statistical Benchmarks
```bash
python -m evaluation.benchmark_runner
```

### 5. Start the Live UI — Two Modes

### ⚡ Single Command Quick Launch (Recommended)
```powershell
.\run.ps1
```
This automatically verifies dependencies, checks ML models, boots both the FastAPI backend and Vite React frontend, and opens `http://localhost:5173` in your default browser.

---

### Manual Launch

**Development (hot-reload, Vite dev server + FastAPI backend):**
```powershell
# Terminal 1 – FastAPI backend
.\venv\Scripts\python.exe -m uvicorn frontend.bridge_server:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 – Vite dev server (proxies /api/* and /ws/* to :8000)
cd frontend
npm run dev
```
Open **`http://localhost:5173`** — React app with hot module replacement.

**Production (FastAPI serves the built bundle):**
```powershell
cd frontend && npm run build   # output → frontend/dist/
cd ..
python -m uvicorn frontend.bridge_server:app --host 0.0.0.0 --port 8000
```
Open **`http://localhost:8000`** — FastAPI serves the built React app via `StaticFiles`.

---

## ✅ Definition of Done Checklist

- [x] 8–12 node topology simulated with packet flow (`network_sim/topology.py`, `network_sim/traffic.py`)
- [x] Fault injector covers all 5 scenario types (`network_sim/fault_injector.py`)
- [x] SNMP agents running per node; poller collects via GET/GETBULK (`network_sim/snmp_agent.py`, `telemetry/snmp_poller.py`)
- [x] SNMP TRAP fires on fault injection (`telemetry/trap_listener.py`)
- [x] Telemetry dataset generated with automated EDA (`ml_engine/dataset_gen.py`, `data/raw/`)
- [x] Isolation Forest + Random Forest trained and evaluated (`ml_engine/isolation_forest.py`, `ml_engine/random_forest.py`)
- [x] Random Forest feature importance extracted and charted to HTML (`data/models/feature_importance.html`)
- [x] Diagnosis + dynamic Dijkstra routing controller working (`self_healing/diagnosis.py`, `self_healing/routing_controller.py`)
- [x] TRAP vs ML alert reconciliation logged to `logs/events.jsonl` (`self_healing/alert_reconciler.py`)
- [x] Static vs self-healing benchmark run N=10x per scenario with mean±std and significance test (`evaluation/benchmark_runner.py`, `logs/benchmark_results.json`)
- [x] Final evaluation report generated (`logs/evaluation_report.html`, `evaluation/report_figures.py`)
- [x] Single-command automated launchers created (`run.ps1`, `run.bat`)

---

## 🛠️ Recent System Hardening & Bug Fixes

A comprehensive multi-phase audit and progressive failure test sequence identified and resolved 9 critical correctness issues across all modules:

1. **State-Transition Alert Deduplication (Member 2 — `ml_engine/inference.py`):**
   - *Problem:* As long as a link stayed congested, the 1-second telemetry poller caused `MLInferenceService` to spam repeated alerts every second.
   - *Fix:* Added link-level state-transition tracking (`last_predicted_state: Dict[str, str]`). Alerts only fire when a link transitions state (e.g. `healthy` $\rightarrow$ `congested`), with state memory automatically cleared on `/api/reset`.

2. **SVG Zero-Dimension Filter Clipping (Member 4 — `frontend/src/components/TopologyGraph.jsx`):**
   - *Problem:* Perfectly vertical edges like `C-D` and `H-I` ($x_1 = x_2$) have an object bounding box width of 0. Under default SVG `filterUnits="objectBoundingBox"`, the browser clipped the line stroke to nothing, making vertical links appear completely disconnected.
   - *Fix:* Switched glow filters to `filterUnits="userSpaceOnUse" x="0" y="0" width="800" height="480"` and synchronized `activePathNodes` fallback to guarantee continuous, unbroken active paths.

3. **Dijkstra Multi-Fault Isolation & Operational Subgraph (Member 3 — `self_healing/routing_controller.py`):**
   - *Problem:* Previously failed edges only accumulated ~7,000 cost penalty while the triggering fault received 1,000,000. Under progressive multiple failures, Dijkstra would route traffic through a previously-failed edge (e.g., `B-F`) because 7,010 was lower than alternate paths.
   - *Fix:* Integrated `nx.subgraph_view` to lazily exclude all down nodes and failed links (`ifOperStatus == 2` or `status == "failed"` or `packet_loss >= 100`) from Dijkstra's graph view, and set failure costs to $10^9$. If the network partitions, active paths are cleanly cleared to empty (`[]`) rather than retaining broken routes.

4. **Latency Sentinel Elimination (Member 1 & 4 — `network_sim/fault_injector.py`, `MetricsPanel.jsx`):**
   - *Problem:* Failed edges had `"latency": 9999.0` written directly to the graph, causing the Live Metrics HUD to display an inflated `Avg RTT Latency` of ~4,709 ms and the topology to render `9999ms`.
   - *Fix:* Removed `9999.0` from `fault_injector.py`, allowing failed links to retain physical baseline latency while marking `ifOperStatus = 2`, `status = "failed"`, and `packet_loss = 100.0`. `MetricsPanel.jsx` now calculates `Avg RTT Latency` strictly over operational links, keeping metrics realistic (~7–8 ms).

5. **Network Partitioning & Unreachable Destination Handling (Member 3 & 4 — `self_healing/routing_controller.py`, `TopologyGraph.jsx`, `RerouteLog.jsx`):**
   - *Problem:* When multiple or progressive faults severed all paths between source $A$ and destination $E$, Dijkstra raised `nx.NetworkXNoPath`. `heal_path` caught the exception but returned `None` silently without publishing a `RerouteEvent`. Consequently, the UI's Reroute Feed retained the stale previous detour (`To: A → B → I → H → D → E`), and the topology graph continued to highlight surviving disconnected segments in cyan alongside failed links.
   - *Fix:* `heal_path` now catches `NetworkXNoPath`/`NodeNotFound` and publishes a `RerouteEvent` with `new_path: []` (empty list) over WebSocket. `TopologyGraph.jsx` added an end-to-end path viability check (`isPathViable`), extinguishing cyan glows on broken paths and displaying a clear status banner: `⚠️ Route Severed: No Surviving Path Available (Destination Unreachable)`. `RerouteLog.jsx` renders a distinct red badge (`Route Severed · Unreachable`) and logs `To: None (No surviving path — Destination Unreachable)`. Added automated unit test `test_routing_controller_unreachable_destination`.

6. **Edge Baseline Restoration & Live Latency Dynamics (Member 1 & 4 — `network_sim/topology.py`, `network_sim/fault_injector.py`, `telemetry/snmp_poller.py`, `TopologyGraph.jsx`, `App.jsx`):**
   - *Problem:* Calling "Restore Network State" (`/api/reset`) wiped every edge's latency in the graph to a hardcoded `8.0` via `reset_faults()`. Even after subsequent link failures, surviving links remained frozen at `8ms`.
   - *Fix:* Stored permanent baseline telemetry (`base_latency`, `base_jitter`, `base_throughput`, `base_utilization`) on each edge during topology generation in `topology.py`. Updated `reset_faults()` in `fault_injector.py` to restore each edge to its own unique `base_latency` rather than overwriting with `8.0`. In `snmp_poller.py`, added realistic dynamic micro-jitter to live telemetry on healthy operational links. Bound live WebSocket telemetry directly to `TopologyGraph.jsx` via `App.jsx`, rendering edge latency numbers dynamically to 1 decimal place (`${Number(currentLatency).toFixed(1)}ms`).

7. **Global React Error Boundary & Crash Protection (Member 4 — `ErrorBoundary.jsx`, `main.jsx`, `MetricsPanel.jsx`):**
   - *Problem:* An unhandled JavaScript render exception (such as `ReferenceError: readings is not defined` inside `MetricsPanel.jsx`) caused React 18/19 to unmount the entire component tree, leaving the user with a completely blacked-out screen.
   - *Fix:* Created `ErrorBoundary.jsx` and wrapped `<App />` in `main.jsx` with an informative error modal and reload button. Restored safe defensive checks on telemetry collections in `MetricsPanel.jsx`.

8. **Launcher Script Path Resilience & Space-Safe Spawning (Launcher Scripts — `run.ps1`, `run.bat`):**
   - *Problem:* Workspace paths containing spaces (e.g. `CN Project`) caused quote-stripping errors when spawning PowerShell background tasks, or batch scripts terminated prematurely after the first process.
   - *Fix:* Updated `run.ps1` to use native `-WorkingDirectory` parameters in `Start-Process`, and updated `run.bat` with `call npm` and `/D` directory flags to guarantee clean, concurrent background server launching on Windows.

9. **Congestion Traversability & Distinct Amber Styling (Member 3 & 4 — `self_healing/routing_controller.py`, `TopologyGraph.jsx`):**
   - *Problem:* Injecting `congestion` on both incoming edges of a leaf node (e.g. `D-E` and `F-E`) caused Dijkstra to prune both edges and falsely trigger `Route Severed: No Surviving Path Available`, while the UI rendered congested edges with red-dashed "failed" styling.
   - *Fix:*
     - In `routing_controller.py`, updated `is_operational_edge()` and `calculate_edge_cost()` to only prune edges or set cost to $10^9$ when `severity >= 0.8` (true hard failures/crashes). Congested edges (`severity < 0.8`) remain fully traversable in the graph view, naturally deprioritized by the dynamic cost formula ($\text{Cost} \approx 200$ vs $\approx 8$) but still usable if no alternate path exists.
     - In `TopologyGraph.jsx`, decoupled alert parsing into `faultedLinks` (hard failures) and `congestedLinks` (`predicted_state === "congested"` / `"degrading"`). Added SVG `<filter id="glow-amber">` and updated edge rendering: congested edges are rendered with solid amber lines (`#f59e0b`), amber glow on active routes, and amber latency readouts (never displaying `'FAILED'`).
     - Added automated regression test `test_routing_controller_congested_edges_remain_traversable` in `tests/test_member_3.py`.


