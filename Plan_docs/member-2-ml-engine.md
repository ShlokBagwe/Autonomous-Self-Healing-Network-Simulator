# Member 2 — Telemetry Dataset, ML Engine, Feature Importance

**Reads first:** `00_PROJECT_MASTER.md` (Sections 4, 5, 6.4, 9) — this file assumes that context and does not repeat the shared schemas or repo layout.

**Owns:** `ml_engine/`
**Branch:** `member-2`

---

## 1. What you are building

The detection brain of the system: a synthetic-but-realistic telemetry dataset, an unsupervised anomaly detector (Isolation Forest), a supervised state classifier (Random Forest), and the feature-importance explainability output.

You sit in the middle of the loop:
`Telemetry Monitor (Member 1) → your ML Engine → Alert → Self-Healing Controller (Member 3)`

You do **not** need to wait for Member 1's real SNMP to exist — build and train against the `TelemetryReading` schema from day one, and your code works unchanged whether the telemetry underneath is in-process (Week 1) or real SNMP (Week 2+).

---

## 2. Files you own

```
ml_engine/
├── dataset_gen.py         # synthetic telemetry generation + EDA
├── isolation_forest.py     # unsupervised anomaly detector
├── random_forest.py        # supervised state classifier
└── feature_importance.py   # explainability deliverable (mandatory)
```

---

## 3. Week-by-week

### Week 1 — Prep (parallel to Member 1's network foundation)

You don't have real telemetry yet, so start on dataset generation and model scaffolding using synthetic data you control directly:

1. `dataset_gen.py`
   - `generate_dataset(n_samples) -> pandas.DataFrame` matching the canonical CSV schema (Master Section 4.1):
     ```
     timestamp,link,latency,jitter,packet_loss,queue,throughput,utilization,state
     ```
   - Generate distinct distributions for `healthy` / `congested` / `failed` (e.g. healthy: low latency/loss, tight variance; congested: elevated latency/queue/loss; failed: latency spike + near-100% loss + near-zero throughput). Include a `degrading` transition pattern for the progressive-degradation fault scenario (gradual worsening across consecutive timestamps on the same link).
   - **Mandatory EDA output**, saved to `data/raw/`:
     - Class balance (counts per `state`)
     - Per-feature distribution plots split by `state` (histograms or box plots)
     - A correlation heatmap across features
   - This EDA is not optional polish — it's what turns "we trained a model" into a defensible analysis in the report/viva.

2. Scaffold `isolation_forest.py` and `random_forest.py` against the synthetic dataset so training/evaluation code is ready the moment Member 1's real telemetry format is confirmed.

### Week 2 — Train, classify, explain (this is your heaviest week)

1. `isolation_forest.py`
   - `train_iforest(df) -> sklearn model` — unsupervised, flags anomalous rows without needing every class labeled. Use this as a first-pass "something's off" signal, independent of the labeled classifier.

2. `random_forest.py`
   - `train_rf(df) -> sklearn model` — classifies `state` (`healthy`/`congested`/`failed`).
   - Save trained model to `data/models/rf.pkl`.
   - Report standard `sklearn.classification_report` (accuracy/precision/recall/F1) — this feeds Member 4's evaluation in Master Section 8.

3. `feature_importance.py` — **mandatory explainability deliverable, do not skip:**
   - `get_feature_importance(model, feature_names) -> pandas.Series` using `model.feature_importances_` (one line — no new pipeline needed).
   - Render as a Plotly bar chart, saved to `data/models/feature_importance.html` — Member 4's frontend embeds this directly.
   - Write one sentence of interpretation for the report, e.g. *"packet loss and RTT dominate failure detection; jitter is the strongest early-warning signal for congestion."* This is the analytical payoff — don't just ship the chart, state what it means.

4. **Live inference (wire into the event bus):**
   - Subscribe to `"telemetry.reading"`.
   - Run each incoming `TelemetryReading` through the trained RF model.
   - Whenever predicted state != `"healthy"`, publish `Alert(source="ml_engine", link=..., predicted_state=..., confidence=<class probability>)` to `"alert.raised"`.
   - This is the **pull-based, proactive** half of the detection system — it runs in parallel with Member 1's TRAP-based **push, reactive** path. Member 3 reconciles both.

**Mid-week checkpoint:** confirm with Member 1 that the real SNMP telemetry (once swapped in) still matches the `TelemetryReading` schema your model was trained against — if poll interval or units shifted, retrain rather than silently degrading accuracy.

### Weeks 3–4

- Week 3: support Member 4 as they embed your feature-importance chart and live alert feed into the dashboard. Fix any latency issues in live inference if it's slowing down the event loop.
- Week 4: support Member 4's benchmark runs — your RF accuracy/precision/recall/F1 numbers get reported as mean ± std across ≥10 runs, not a single number (Master Section 8). If time permits, add SHAP as an optional second explainability layer on top of feature importance (Master Section 6, "Explainable AI" row) — feature importance is the fast baseline that ships regardless.

---

## 4. Contracts you must not break

- Train and predict using the exact `TelemetryReading` field names/types from Master Section 5.
- Every `Alert` you publish must set `source="ml_engine"` and include a `confidence` value — Member 3's reconciler and Member 4's alert feed both depend on distinguishing ML alerts from TRAP alerts.
- Feature importance chart must be saved to `data/models/feature_importance.html` — that exact path is what Member 4's frontend loads.
- Never import from `network_sim/`, `self_healing/`, or `frontend/` — only `shared/`.

## 5. Definition of done (your slice)

- [ ] Synthetic dataset generated matching the canonical CSV schema, with EDA (class balance, distributions, correlation heatmap)
- [ ] Isolation Forest trained (unsupervised anomaly flag)
- [ ] Random Forest trained and saved to `data/models/rf.pkl`, with classification report
- [ ] Feature importance extracted and charted to `data/models/feature_importance.html`, with one-sentence interpretation
- [ ] Live inference subscribed to `"telemetry.reading"`, publishing `Alert(source="ml_engine", ...)` to `"alert.raised"`
