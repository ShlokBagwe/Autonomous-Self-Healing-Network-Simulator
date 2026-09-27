# Member 4 — Frontend, Evaluation, Benchmarking, Report

**Reads first:** `00_PROJECT_MASTER.md` (Sections 5, 6.6, 6.7, 8, 9) — this file assumes that context and does not repeat the shared schemas or repo layout.

**Owns:** `frontend/`, `evaluation/`
**Branch:** `member-4`

---

## 1. What you are building

Two things that come together at the end: a live dashboard that makes the whole self-healing loop visible, and the benchmarking harness that produces the project's actual evidence (static routing vs. self-healing, with statistics, not vibes).

You are the **last** consumer in the loop and also its verifier:
`Everyone's event bus topics → your Frontend (visualize) and your Evaluation (measure, compare, prove)`

You depend on Members 1–3 publishing correctly to the event bus, but you can build your UI skeleton and your metrics math independently, using dummy events, before their real modules are ready.

---

## 2. Files you own

## 2a. Frontend Bridge Layer (new — required for React)

Since the frontend is now React + Tailwind CSS instead of Streamlit/Dash, you need a bridge server between the Python event bus and the browser. React cannot subscribe to `shared/event_bus.py` directly.

**New file you own:** `frontend/bridge_server.py`

- Use FastAPI (async-native, small, pairs cleanly with WebSocket).
- Subscribe to `"telemetry.reading"`, `"alert.raised"`, `"reroute.completed"` on the Python event bus.
- Relay each as a JSON message over a WebSocket endpoint (`ws://localhost:8000/ws/events`), tagged with a `type` field and a `payload` matching the shared dataclass shape (see Master Section 6.8 for exact message format — do not diverge from it, Member 3's reconciliation data and Member 2's alert confidence values both depend on the payload shape staying consistent).
- Expose REST endpoints for one-off actions:
  - `POST /api/fault` → calls Member 1's `inject_fault()`, used by your React fault-injection buttons.
  - `GET /api/feature-importance` → serves Member 2's saved feature-importance output.
  - `GET /api/reconciliation` → serves Member 3's TRAP/ML reconciliation records from `logs/events.jsonl`.

**Build order:**
1. Week 1: scaffold `bridge_server.py` with dummy/mocked events so your React skeleton has something to connect to before real data exists.
2. Week 3 (same checkpoint as before): connect it to the real event bus and confirm all 5 fault scenarios are visible end-to-end through the actual React UI, not just the bridge's raw WebSocket output.

**Contract reminder:** the bridge must stay a pure relay — no diagnosis, routing, or ML logic belongs in it. If you find yourself computing something in `bridge_server.py` instead of just forwarding it, that logic belongs in someone else's module instead.

```
frontend/
├── app.py               
└── components/           # topology view, charts, alert feed, etc.
evaluation/
├── benchmark_runner.py    # runs scenarios N times under both routing modes
├── metrics.py              # MTTD, MTTR, PDR, etc. + significance testing
└── report_figures.py       # final comparison charts
```

---

## 3. Week-by-week

### Week 1 — Skeleton (parallel to everyone else)

You have no real data yet, so build structure against dummy/mocked events:

1. `frontend/app.py`
   - Streamlit is the default choice (fastest to build, Python-only); switch to Dash only if the team agrees — the subscribe-to-event-bus interface stays identical either way.
   - Lay out the skeleton: a topology panel, a live metrics panel (latency/loss/queue/jitter), a fault-injection control panel, an alert feed panel, a rerouted-path highlight, and a slot for Member 2's feature-importance chart.
   - Wire each panel to subscribe to the relevant bus topic (`"telemetry.reading"`, `"alert.raised"`, `"reroute.completed"`) even before real publishers exist — publish dummy events yourself to test rendering.

2. `evaluation/metrics.py`
   - Implement the metric formulas now, against synthetic/dummy event logs, so they're proven correct before real data arrives:
     - `MTTD = t_detected - t_fault_onset` (first of ML or TRAP)
     - `MTTR = t_recovered - t_fault_onset`
     - `SNMP TRAP latency = t_trap_received - t_fault_onset` (compare distribution to MTTD)
     - `PDR = successful_packets / total_packets`
     - Average latency, throughput recovery time
     - RF accuracy/precision/recall/F1 via `sklearn.classification_report` (reads Member 2's saved model output)
   - Every function should read from `logs/events.jsonl` or take a `TelemetryReading`/`Alert`/`RerouteEvent` list directly — never from another member's internal state.

### Week 2 — Support, don't block

This week belongs to Members 1–3 getting the core loop working end-to-end. Your job:
- Keep refining `metrics.py` against whatever real (or dummy) `logs/events.jsonl` entries start appearing.
- Do **not** wait idle — start `benchmark_runner.py`'s scaffolding: a loop that calls Member 1's `fault_injector.inject_fault()` N times per scenario under two conditions (static routing baseline vs. self-healing enabled), varying the random seed each run (Member 1's `build_topology(seed=...)`).

### Week 3 — Full frontend integration

1. Wire the dashboard live against the real event bus:
   - **Topology view:** current graph state, highlighting the currently-active route and any failed/congested elements.
   - **Live charts:** latency/loss/queue/jitter over time, sourced from `"telemetry.reading"`.
   - **Fault-injection controls:** buttons that call Member 1's `inject_fault()` for each of the 5 scenario types.
   - **Alert feed:** source-tagged (TRAP vs ML) list from `"alert.raised"`, ideally also showing Member 3's reconciliation `agreement` flag from `logs/events.jsonl`.
   - **Rerouted-path highlight:** from `"reroute.completed"`.
   - **Feature-importance chart:** embed Member 2's saved `data/models/feature_importance.html` directly.

2. **Checkpoint (Master Section 9):** all 5 fault scenarios must be demonstrable end-to-end through the UI by end of Week 3.

### Week 4 — Benchmark, prove it, report

1. `benchmark_runner.py`
   - Run every fault scenario **N ≥ 10 times** under both static routing and self-healing, varying the random seed per run (Master Section 6.7). Do not report a single-run number as a result — this is a hard requirement (Master Section 8).

2. `metrics.py`
   - For each metric, compute **mean ± std** across runs for both conditions.
   - Run a significance test between static vs. self-healing per metric using `scipy.stats.mannwhitneyu`.
   - Report RF accuracy/precision/recall/F1 alongside, from Member 2's model.

3. `report_figures.py`
   - Generate the final comparison charts (static vs. self-healing, per metric, with error bars) for the report/demo/PPT.
   - Include the SNMP-TRAP-latency-vs-MTTD comparison as its own figure — this is the project's most distinctive result (reactive vs. proactive detection), built from Member 3's reconciliation data.

---

## 4. Contracts you must not break

- Never read Member 1/2/3's internal module state — only their published event bus topics and `logs/events.jsonl`.
- Every headline metric must be reported as mean ± std across ≥10 runs with a significance test, not a single-run number (Master Section 8) — this is a hard project requirement, not a nice-to-have.
- `benchmark_runner.py` must vary the random seed per run via Member 1's `build_topology(seed=...)` — identical seeds across runs invalidate the significance test.
- Feature-importance chart must be loaded from the exact path Member 2 saves it to: `data/models/feature_importance.html`.

## 5. Definition of done (your slice)

- [ ] Dashboard shows: live topology, live metric charts, fault-injection controls, source-tagged alert feed, rerouted-path highlight, feature-importance chart
- [ ] All 5 fault scenarios demonstrable end-to-end through the UI
- [ ] Benchmark runner executes ≥10 runs per scenario under both static and self-healing routing, varied seeds
- [ ] `metrics.py` computes MTTD, MTTR, TRAP latency, PDR, avg latency, throughput recovery, RF accuracy/precision/recall/F1 — all as mean ± std with significance testing
- [ ] Final comparison charts generated, including the TRAP-latency-vs-MTTD figure
