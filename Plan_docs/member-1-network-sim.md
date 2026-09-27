# Member 1 — Network Simulation, Fault Injector, SNMP Agents & Polling

**Reads first:** `00_PROJECT_MASTER.md` (Sections 3, 4, 5, 6.1–6.3, 9) — this file assumes that context and does not repeat the shared schemas or repo layout.

**Owns:** `network_sim/`, `telemetry/`
**Branch:** `member-1`

---

## 1. What you are building

The foundation everyone else builds on: a virtual network graph, traffic flowing across it, a way to break it on demand, and — starting Week 2 — real SNMP agents that expose telemetry over localhost UDP instead of plain function calls.

You are the **first** link in the core loop:
`Virtual Network → SNMP Agents → Telemetry Monitor → (publishes to event bus)`

Everything downstream (Member 2's ML, Member 3's self-healing, Member 4's frontend) consumes what you publish. If your `TelemetryReading` objects don't match the schema in Master Section 5 exactly, nothing downstream will run.

---

## 2. Files you own

```
network_sim/
├── topology.py        # graph construction
├── traffic.py          # packet flow simulation
├── fault_injector.py   # breaks things on demand
└── snmp_agent.py        # per-node SNMP agent (Week 2+)
telemetry/
├── snmp_poller.py       # polls agents, publishes TelemetryReading
└── trap_listener.py     # listens for TRAPs, publishes Alert
```

---

## 3. Week-by-week

### Week 1 — Network foundation (in-process telemetry)

**Goal:** working 8–12 node simulator with packet flow and fault injection, telemetry collection built **behind the exact interface SNMP will replace in Week 2.**

1. `topology.py`
   - `build_topology(n_nodes=10) -> networkx.Graph`
   - Nodes labeled `"A"`, `"B"`, ... Edges weighted with `base_cost`.
   - Store per-edge state needed for the dynamic cost formula: `base_cost, latency, packet_loss, congestion_level, failure_risk`.
   - Edge cost formula (used everywhere downstream, including Member 3's routing controller):
     ```
     cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty
     ```

2. `traffic.py`
   - Simulate packet flow across the graph (SimPy recommended). Traffic should be continuous enough that a fault visibly disrupts delivery — this is what Member 4's PDR metric measures.
   - Expose a simple `send_packet(src, dst) -> bool` (delivered or dropped) so Member 4's benchmark runner can drive traffic without touching your internals.

3. `fault_injector.py`
   - `inject_fault(graph, kind, target) -> None` where `kind` is one of `"link_failure"`, `"router_crash"`, `"congestion"`, `"degradation"`, `"multi_fault"`.
   - Each kind mutates the relevant edge/node state (e.g. `link_failure` sets an edge's `failure_risk` to max and marks it unusable; `congestion` spikes `congestion_level`).
   - **Critical:** every call must record `t_fault_onset` (simulation timestamp) somewhere retrievable — Member 4's MTTD/MTTR metrics are computed relative to this timestamp. Simplest approach: publish a `"fault.injected"` event on the bus with `{timestamp, kind, target}`.

4. **Telemetry — build the interface now, even though it's in-process this week:**
   ```python
   # telemetry/snmp_poller.py (Week 1 version — no real SNMP yet)
   def poll_all_nodes() -> list[TelemetryReading]:
       # reads directly from the graph/traffic state this week
       # MUST return objects matching shared.schemas.TelemetryReading exactly
       ...
   ```
   Call this every `POLL_INTERVAL_SEC` (from `shared/config.py`) and `bus.publish("telemetry.reading", reading)` for each one. **This is the function Week 2 will swap the internals of — the signature and return type must not change.** Do not let any other module read graph state directly; force everything through this function, or the Week 2 swap becomes a rewrite.

**End of Week 1 checkpoint:** Member 2, 3, and 4 can subscribe to `"telemetry.reading"` and `"fault.injected"` and see realistic-looking data flowing, even though it's not real SNMP yet.

### Week 2 — Real SNMP (GET/GETBULK + TRAP)

1. `snmp_agent.py`
   - One `pysnmp` agent per node, each on `localhost:<161XX>` (e.g. node A → 16101, node B → 16102...).
   - Exposes the OID map from Master Section 4.2 (`shared/config.py: OID_MAP`).
   - `fire_trap(target) -> None` — sends an SNMP TRAP immediately. **This must be called from `fault_injector.inject_fault()` at the exact moment of injection** — this is the reactive alert path Member 3 depends on for TRAP/ML reconciliation.

2. `snmp_poller.py` — rewrite internals only, keep the signature identical:
   ```python
   def poll_all_nodes() -> list[TelemetryReading]:
       # now performs real SNMP GET/GETBULK against each node's agent
       # same return type as Week 1 — downstream code does not change
       ...
   ```

3. `trap_listener.py`
   - Listens for incoming TRAPs, builds `Alert(source="snmp_trap", link=..., predicted_state="failed", confidence=None)`, publishes to `"alert.raised"`.

**Mid-week checkpoint (Master Section 9):** confirm the SNMP poll interval hasn't silently changed timestamp granularity in a way that breaks Member 2's ML training data or Member 4's MTTD calculation. Poll interval is fixed at `POLL_INTERVAL_SEC = 1.0s` — this is a known floor on MTTD; do not let anyone report MTTD below this without noting it (see Master Section 4.2 and 8).

**End of Week 2 checkpoint:** full detect→reroute loop works end-to-end on at least one fault type, using real SNMP for telemetry and TRAPs.

### Weeks 3–4

- Week 3: support Member 4 as they wire the frontend to your event bus topics. Fix any timing/race issues surfaced by continuous UI polling.
- Week 4: support Member 4's benchmark runs (≥10 runs/scenario) — make sure `build_topology()` accepts a `seed` parameter so runs are reproducible and varied per Master Section 6.7.

---

## 4. Contracts you must not break

- `TelemetryReading` fields and types exactly as in Master Section 5 — Member 2's model training and Member 4's evaluation both assume this shape.
- `inject_fault()` must always call `snmp_agent.fire_trap()` at the moment of injection (Week 2+) — this is the entire basis of the TRAP-vs-ML comparison metric.
- Publish `t_fault_onset` for every injected fault — every headline metric in Master Section 8 is computed relative to it.
- Never import from `ml_engine/`, `self_healing/`, or `frontend/` — only `shared/`.

## 5. Definition of done (your slice)

- [ ] 8–12 node topology with weighted edges and the shared cost formula
- [ ] Traffic flowing continuously across the graph
- [ ] All 5 fault types implemented and individually testable
- [ ] Week 1: in-process telemetry behind the exact `TelemetryReading` interface
- [ ] Week 2: real SNMP agents per node, GET/GETBULK polling, TRAP firing on fault
- [ ] `t_fault_onset` recorded/published for every fault
