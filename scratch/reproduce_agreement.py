import sys, os
sys.path.insert(0, os.path.abspath("."))
import time
from shared.config import TOPIC_ALERT, TOPIC_TELEMETRY
from shared.event_bus import bus
from network_sim.topology import build_topology
from network_sim.fault_injector import FaultInjector
from telemetry.snmp_poller import poll_all_nodes
from ml_engine.inference import MLInferenceService
from self_healing.alert_reconciler import AlertReconciler

def reproduce_scenario():
    # Fresh bus subscriptions
    g = build_topology(n_nodes=10, seed=42)
    inj = FaultInjector(g)
    ml_service = MLInferenceService(auto_subscribe=True)
    reconciler = AlertReconciler(auto_subscribe=True)

    collected_alerts = []
    def alert_listener(alert):
        collected_alerts.append(alert)

    bus.subscribe(TOPIC_ALERT, alert_listener)

    # Pre-poll once healthy
    t = 100.0
    poll_all_nodes(g, timestamp=t)

    print("Step 1: Injecting degradation on D-E at t=101.0")
    inj.inject("degradation", "D-E")
    
    # Poll a few cycles so D-E degrades enough for ML engine to detect
    for i in range(1, 5):
        t = 101.0 + i
        readings = poll_all_nodes(g, timestamp=t)
        # ML service automatically gets telemetry from poll_all_nodes via event bus
    
    print(f"Alerts after D-E degradation: {len(collected_alerts)}")
    for a in collected_alerts:
        print(f"  Alert: link={a.link}, source={a.source}, state={a.predicted_state}, conf={a.confidence}, ts={a.timestamp}")

    print("\nStep 2: Injecting link_failure on E-F at t=106.0 while D-E is still degrading")
    inj.inject("link_failure", "E-F")
    t = 106.0
    readings = poll_all_nodes(g, timestamp=t)

    print(f"\nTotal Alerts collected during scenario: {len(collected_alerts)}")
    print("-" * 80)
    for idx, a in enumerate(collected_alerts):
        print(f"[{idx}] link={a.link:5s} | source={a.source:10s} | state={a.predicted_state:10s} | conf={a.confidence} | ts={a.timestamp:.2f}")
    print("-" * 80)

    # Check python AlertReconciler records
    print("\nPython AlertReconciler history:")
    print(f"Reconciliation records in reconciler.reconciliation_history: {len(reconciler.reconciliation_history)}")
    for r in reconciler.reconciliation_history:
        print(f"  Record: link={r.link}, agreement={r.agreement}, sources={r.sources}, trap_ts={r.trap_timestamp}, ml_ts={r.ml_timestamp}")

    print(f"Reconciler unpaired pending alerts: {reconciler.unpaired_alerts}")
    stats = reconciler.get_summary_stats()
    print(f"Reconciler summary stats: {stats}")

    # Check frontend MetricsPanel.jsx calculation
    trap_count = len([a for a in collected_alerts if a.source == "snmp_trap"])
    ml_count = len([a for a in collected_alerts if a.source == "ml_engine"])
    total = trap_count + ml_count
    frontend_agreement_rate = min(trap_count, ml_count) / max(trap_count, ml_count) if max(trap_count, ml_count) > 0 else 0
    print(f"\nFrontend MetricsPanel.jsx calculation:")
    print(f"  trapAlerts count = {trap_count}")
    print(f"  mlAlerts count   = {ml_count}")
    print(f"  frontend agreement rate = {frontend_agreement_rate * 100:.1f}%")

if __name__ == "__main__":
    reproduce_scenario()
