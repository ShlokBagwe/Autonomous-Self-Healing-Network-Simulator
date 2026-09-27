# Member 3 — Diagnosis, Self-Healing Controller, TRAP/ML Reconciliation

**Reads first:** `00_PROJECT_MASTER.md` (Sections 5, 6.1, 6.5, 9) — this file assumes that context and does not repeat the shared schemas or repo layout.

**Owns:** `self_healing/`
**Branch:** `member-3`

---

## 1. What you are building

The decision-maker: given an alert (from either Member 1's SNMP TRAP or Member 2's ML engine), figure out what's actually wrong, recalculate the best surviving route, and redirect traffic. You also own the single most research-valuable piece of this project — **reconciling the two independent alert sources** (reactive TRAP vs. proactive ML) into comparison data.

You sit at the busiest junction in the loop:
`Alert (from Member 1 TRAP or Member 2 ML) → your Diagnosis → your Routing Controller → RerouteEvent → Member 4's dashboard/evaluation`

You can start building against **dummy alerts** before Member 1's real SNMP or Member 2's trained model exist — just publish fake `Alert` objects matching the schema and confirm your pipeline reacts correctly. This is explicitly allowed per Master Section 9, Week 2.

---

## 2. Files you own

```
self_healing/
├── alert_reconciler.py     # TRAP vs ML comparison — your most important deliverable
├── diagnosis.py             # figure out what's actually wrong
└── routing_controller.py    # recalculate + reroute
```

---

## 3. Week-by-week

### Week 1 — Prep (parallel to Members 1 and 2)

You have no real alerts yet, so:

1. Read and internalize Member 1's edge cost formula (Master Section 6.1) — your routing controller depends on it exactly:
   ```
   cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty
   ```
2. Scaffold `routing_controller.py` against a locally-built toy `networkx.Graph` so your Dijkstra logic is proven before real topology exists.
3. Scaffold `diagnosis.py` and `alert_reconciler.py` against hand-written dummy `Alert` objects (matching Master Section 5's schema) so your pipeline logic is ready to plug into the real event bus the moment Members 1 and 2 publish real ones.

### Week 2 — Build against the real event bus (this is your heaviest week)

1. `alert_reconciler.py` — **build this first, it's your most important file:**
   - Subscribe to `"alert.raised"`.
   - Log every incoming `Alert` with its `source` (`"snmp_trap"` or `"ml_engine"`).
   - If both a TRAP alert and an ML alert arrive for the **same `link`** within a short time window (define a constant, e.g. `RECONCILE_WINDOW_SEC = 2.0`, in your module), record `agreement=True` and both timestamps.
   - If only one source fires, record which one and its timestamp alone.
   - This produces the raw data behind the **SNMP TRAP latency vs. MTTD** comparison metric (Master Section 8) — write these reconciliation records to `logs/events.jsonl` (append, `type: "reconciliation"`) so Member 4's evaluation scripts can read them without needing your internals.

2. `diagnosis.py`
   - `diagnose(alert: Alert, graph) -> (affected_element, severity)`.
   - `affected_element` is the specific node/link from `alert.link`. `severity` should reflect how bad it is (e.g. derived from `alert.confidence` for ML alerts, or treated as maximum severity for TRAP alerts since a TRAP means the agent is unreachable/failed).

3. `routing_controller.py`
   - `recalculate_route(graph, source, dest, failed_element) -> list[str]` — mark the failed element unusable (or heavily penalized, depending on fault severity) and use **NetworkX Dijkstra** with the shared dynamic edge-cost formula to find the best surviving path. Do not use A* — the project spec calls for Dijkstra specifically (Master Section 1).
   - Once a new path is found, publish `RerouteEvent(timestamp, failed_link, old_path, new_path, trigger_alert, recovery_latency_ms)` to `"reroute.completed"`. Compute `recovery_latency_ms` relative to the `t_fault_onset` Member 1 published (Master Section 6.2) — this is the raw data behind MTTR.

**Mid-week checkpoint:** confirm with Member 1 and Member 2 that real alerts (TRAP and ML) are flowing correctly into your reconciler and producing sensible `agreement` records — this is the piece most likely to reveal integration bugs (see Master Section 9).

**End of Week 2 checkpoint:** the full detect→reroute loop works end-to-end on at least one fault type (e.g. link failure), with your module correctly diagnosing, rerouting, and reconciling alert sources.

### Weeks 3–4

- Week 3: support Member 4 as they surface your reroute events and TRAP-vs-ML reconciliation data on the dashboard (source-tagged alert feed, rerouted-path highlight).
- Week 4: support Member 4's benchmark runs — your `recovery_latency_ms` and reconciliation records are the direct inputs to the MTTR and TRAP-latency-vs-MTTD metrics (Master Section 8), reported as mean ± std with a significance test across ≥10 runs per scenario.

---

## 4. Contracts you must not break

- Only act on `Alert` objects received via `"alert.raised"` — never read Member 1's or Member 2's internal state directly.
- Every successful reroute must publish a `RerouteEvent` with all fields populated, including `recovery_latency_ms` relative to `t_fault_onset`.
- Reconciliation records must be appended to `logs/events.jsonl` — this is the only place Member 4's evaluation reads TRAP-vs-ML comparison data from.
- Routing uses NetworkX Dijkstra with the shared edge-cost formula — do not substitute A* or a different cost model without updating Master Section 6.1 first (Master Section 12: shared interfaces are immutable once Week 1 ends without a documented change).
- Never import from `network_sim/`, `ml_engine/`, or `frontend/` — only `shared/`.

## 5. Definition of done (your slice)

- [ ] `alert_reconciler.py` logging every alert by source, with TRAP/ML agreement detection within the reconcile window
- [ ] `diagnosis.py` mapping alerts to affected element + severity
- [ ] `routing_controller.py` recalculating routes via Dijkstra + shared cost formula, publishing `RerouteEvent`
- [ ] Full detect → diagnose → reroute loop demonstrable on all 5 fault scenarios
- [ ] Reconciliation records written to `logs/events.jsonl` for Member 4's TRAP-latency-vs-MTTD metric
