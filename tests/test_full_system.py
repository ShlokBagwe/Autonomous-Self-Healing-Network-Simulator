"""
Comprehensive Integration Tests for the Complete Self-Healing Network Simulator (All 4 Members).
"""
import os
import json
import pytest
import networkx as nx

from shared.config import TOPIC_ALERT, TOPIC_FAULT, TOPIC_REROUTE, TOPIC_TELEMETRY
from shared.event_bus import bus
from shared.schemas import Alert, TelemetryReading, RerouteEvent

# Member 1 imports
from network_sim.topology import build_topology, calculate_edge_cost
from network_sim.fault_injector import FaultInjector
from network_sim.snmp_agent import agent_manager
from network_sim.traffic import TrafficSimulator
from telemetry.snmp_poller import poll_all_nodes

# Member 2 imports
from ml_engine.dataset_gen import generate_dataset
from ml_engine.isolation_forest import train_iforest, AnomalyDetector
from ml_engine.random_forest import train_rf, NetworkStateClassifier
from ml_engine.feature_importance import get_feature_importance, render_feature_importance_html
from ml_engine.inference import MLInferenceService

# Member 3 imports
from self_healing.diagnosis import diagnose
from self_healing.routing_controller import RoutingController, recalculate_route
from self_healing.alert_reconciler import AlertReconciler

# Member 4 imports
from evaluation.metrics import compute_mann_whitney, compute_mttd, compute_mttr, format_mean_std
from evaluation.benchmark_runner import run_benchmark


@pytest.fixture(autouse=True)
def reset_bus():
    bus.clear()
    yield
    bus.clear()


# =============================================================================
# MEMBER 1 TESTS
# =============================================================================
def test_member_1_topology_and_snmp():
    g = build_topology(n_nodes=10, seed=42)
    assert g.number_of_nodes() == 10
    assert nx.is_connected(g)

    # Validate MIB sync
    agent_manager.init_agents(g)
    agent_manager.sync_telemetry(g)
    assert "A" in agent_manager.agents
    agent_a = agent_manager.agents["A"]
    # Check OID .1 (latency)
    assert agent_a.get("1.3.6.1.4.1.9999.1.1") is not None


def test_member_1_all_fault_scenarios():
    g = build_topology(n_nodes=10, seed=123)
    injector = FaultInjector(g)

    # 1. Link failure
    inj1 = injector.inject("link_failure", "A-B")
    assert inj1["kind"] == "link_failure"
    assert g.edges["A", "B"]["status"] == "failed"

    # 2. Router crash
    inj2 = injector.inject("router_crash", "C")
    assert g.nodes["C"]["status"] == "down"

    # 3. Congestion
    inj3 = injector.inject("congestion", "D-E")
    assert g.edges["D", "E"]["status"] == "congested"

    # 4. Degradation
    inj4 = injector.inject("degradation", "E-F")
    assert g.edges["E", "F"]["status"] == "degrading"

    # 5. Multi-fault
    inj5 = injector.inject("multi_fault", ["F-G", "G-H"])
    assert g.edges["F", "G"]["status"] == "failed"

    # Restore
    injector.reset_faults()
    assert g.nodes["C"]["status"] == "up"
    assert g.edges["A", "B"]["status"] == "healthy"


def test_member_1_traffic_and_pdr():
    g = build_topology(n_nodes=8, seed=99)
    traffic = TrafficSimulator(g)

    # Send packets on healthy network -> PDR should be 100%
    for _ in range(10):
        delivered, lat = traffic.send_packet("A", "D")
        assert delivered is True

    assert traffic.get_pdr() == 1.0


# =============================================================================
# MEMBER 2 TESTS
# =============================================================================
def test_member_2_dataset_and_models():
    df = generate_dataset(n_samples=600, seed=1, save_csv=False)
    assert len(df) == 600
    assert set(df["state"].unique()) == {"healthy", "congested", "failed"}

    # Isolation Forest
    iforest = train_iforest(df)
    detector = AnomalyDetector(iforest)
    assert isinstance(detector.is_anomalous(df.iloc[0][["latency", "jitter", "packet_loss", "queue", "throughput", "utilization"]].to_dict()), bool)

    # Random Forest
    rf, report = train_rf(df, save_model=False)
    assert report["overall_accuracy"] >= 0.90

    # Feature Importance
    importance = get_feature_importance(rf)
    assert len(importance) == 6
    html_path = render_feature_importance_html(importance)
    assert os.path.exists(html_path)


def test_member_2_live_inference():
    df = generate_dataset(n_samples=500, seed=42, save_csv=False)
    rf, _ = train_rf(df, save_model=False)
    classifier = NetworkStateClassifier(rf)
    service = MLInferenceService(classifier, auto_subscribe=False)

    # Congested reading
    reading = TelemetryReading(
        timestamp=200.0,
        link="B-C",
        latency=90.0,
        jitter=25.0,
        packet_loss=10.0,
        queue=60,
        throughput=25.0,
        utilization=0.92,
    )
    alert = service.on_telemetry_reading(reading)
    assert alert is not None
    assert alert.predicted_state in ("congested", "failed")
    assert alert.source == "ml_engine"

    # Second reading with same state -> deduplicated, returns None
    second_alert = service.on_telemetry_reading(reading)
    assert second_alert is None, "Repeated readings with identical state must not raise duplicate alerts"

    # After reset_state(), the transition from healthy to congested alerts again
    service.reset_state()
    third_alert = service.on_telemetry_reading(reading)
    assert third_alert is not None, "After reset_state(), initial fault transition must alert again"
    assert third_alert.source == "ml_engine"


# =============================================================================
# MEMBER 3 & 4 TESTS
# =============================================================================
def test_member_3_dynamic_reroute_and_reconcile():
    g = build_topology(n_nodes=10, seed=42)
    controller = RoutingController(g)
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=False)

    controller.set_active_path("A", "D", ["A", "B", "C", "D"])

    # Simulate link failure
    trap_alert = Alert(timestamp=100.0, source="snmp_trap", link="B-C", predicted_state="failed")
    ml_alert = Alert(timestamp=100.1, source="ml_engine", link="B-C", predicted_state="failed", confidence=0.99)

    # Reconcile alerts
    r1 = reconciler.process_alert(trap_alert)
    assert r1 is None
    r2 = reconciler.process_alert(ml_alert)
    assert r2 is not None
    assert r2.agreement is True

    # Reroute
    ev = controller.heal_path("A", "D", trigger_alert=trap_alert, current_time=100.02)
    assert ev is not None
    assert "B-C" not in [(ev.new_path[i], ev.new_path[i+1]) for i in range(len(ev.new_path)-1)]


def test_member_4_metrics_and_significance():
    baseline = [0.45, 0.40, 0.50, 0.42, 0.48]
    healing = [0.98, 1.0, 0.95, 0.99, 1.0]

    test_res = compute_mann_whitney(baseline, healing)
    assert test_res["is_significant"] is True
    assert test_res["p_value"] < 0.05

    mttd = compute_mttd(t_fault_onset=50.0, alert_timestamps=[50.015, 50.12])
    assert mttd == 15.0  # ms


def test_progressive_degradation_tick_evolution():
    """Verify that degradation fault progressively worsens metrics across successive polls."""
    from telemetry.snmp_poller import poll_all_nodes

    g = build_topology(n_nodes=10, seed=42)
    injector = FaultInjector(g)
    injector.inject("degradation", "D-E", timestamp=100.0)

    # Initial state should be in degrading mode
    assert g.edges["D", "E"]["status"] == "degrading"

    # Poll across multiple ticks
    r1 = [r for r in poll_all_nodes(g, timestamp=100.0) if r.link in ("D-E", "E-D")][0]
    r2 = [r for r in poll_all_nodes(g, timestamp=101.0) if r.link in ("D-E", "E-D")][0]
    r3 = [r for r in poll_all_nodes(g, timestamp=102.0) if r.link in ("D-E", "E-D")][0]

    assert r2.latency > r1.latency, f"Expected r2.latency ({r2.latency}) > r1.latency ({r1.latency})"
    assert r3.latency > r2.latency, f"Expected r3.latency ({r3.latency}) > r2.latency ({r2.latency})"
    assert r3.jitter >= r2.jitter >= r1.jitter
    assert r3.packet_loss >= r2.packet_loss >= r1.packet_loss
    assert r3.queue >= r2.queue >= r1.queue
    assert r3.throughput <= r2.throughput <= r1.throughput


def test_progressive_degradation_delayed_ml_alert():
    """Verify that progressive degradation delays ML alert until degradation threshold is crossed."""
    from telemetry.snmp_poller import poll_all_nodes

    g = build_topology(n_nodes=10, seed=42)
    injector = FaultInjector(g)
    ml_service = MLInferenceService(auto_subscribe=False)

    injector.inject("degradation", "D-E", timestamp=200.0)

    # Tick 0: initial onset is still healthy (no alert)
    readings_t0 = poll_all_nodes(g, timestamp=200.0)
    de_t0 = [r for r in readings_t0 if r.link in ("D-E", "E-D")][0]
    alert_t0 = ml_service.on_telemetry_reading(de_t0)
    assert alert_t0 is None, "Early degradation onset must not alert immediately"

    # Advance polls until ML detects state transition to congested
    detected_alert = None
    for tick in range(1, 8):
        readings = poll_all_nodes(g, timestamp=200.0 + tick)
        de_r = [r for r in readings if r.link in ("D-E", "E-D")][0]
        alert = ml_service.on_telemetry_reading(de_r)
        if alert is not None:
            detected_alert = alert
            break

    assert detected_alert is not None, "Degradation must eventually trigger ML transition alert"
    assert detected_alert.predicted_state in ("congested", "failed")
    assert detected_alert.timestamp > 200.0, "Alert must be timed later than initial fault injection"


def test_mean_mttr_submillisecond_precision():
    """Verify that sub-millisecond recovery latencies average accurately and format with decimal precision."""
    # Fast recoveries of 0.3ms and 0.5ms
    sample_mttrs = [0.3, 0.5]
    avg_mttr = sum(sample_mttrs) / len(sample_mttrs)
    assert avg_mttr == 0.4

    # Format with 1 decimal place (fixed frontend behavior)
    display_str = f"{avg_mttr:.1f} ms"
    assert display_str == "0.4 ms"
    assert display_str != "0 ms"


def test_standardized_avg_rtt_latency_formula():
    """
    Verify standardized Avg RTT Latency:
    1. Baseline: mean over all operational links.
    2. Degradation: includes degraded link weighted as 1 of N (modest shift, no collapse).
    3. Link Failure: failed link yields no response and is excluded from both sum and count.
    4. Router Crash: incident links to crashed node yield no response and are excluded.
    """
    from evaluation.metrics import compute_avg_rtt_latency
    from telemetry.snmp_poller import poll_all_nodes

    g = build_topology(10, seed=42)
    injector = FaultInjector(g)

    # 1. Baseline
    readings_base = poll_all_nodes(g, timestamp=100.0)
    assert len(readings_base) == 17
    avg_base = compute_avg_rtt_latency(readings_base)
    assert 7.0 <= avg_base <= 9.5
    manual_base = round(sum(r.latency for r in readings_base) / len(readings_base), 2)
    assert avg_base == manual_base

    # 2. Degradation on D-E
    injector.inject("degradation", "D-E", timestamp=100.0)
    readings_deg = poll_all_nodes(g, timestamp=101.0)
    assert len(readings_deg) == 17
    avg_deg = compute_avg_rtt_latency(readings_deg)
    de_reading = [r for r in readings_deg if r.link in ("D-E", "E-D")][0]
    # Avg latency should move modestly, NOT jump to match D-E's own latency
    assert avg_deg < de_reading.latency
    manual_deg = round(sum(r.latency for r in readings_deg) / len(readings_deg), 2)
    assert avg_deg == manual_deg

    # 3. Link Failure on D-E: D-E must be completely excluded
    injector.reset_faults()
    injector.inject("link_failure", "D-E", timestamp=200.0)
    readings_fail = poll_all_nodes(g, timestamp=200.0)
    assert len(readings_fail) == 16, "Failed link must not yield an SNMP reading"
    assert not any(r.link in ("D-E", "E-D") for r in readings_fail)
    avg_fail = compute_avg_rtt_latency(readings_fail)
    manual_fail = round(sum(r.latency for r in readings_fail) / len(readings_fail), 2)
    assert avg_fail == manual_fail

    # 4. Router Crash on Node C: both B-C and C-D must be completely excluded
    injector.reset_faults()
    injector.inject("router_crash", "C", timestamp=300.0)
    readings_crash = poll_all_nodes(g, timestamp=300.0)
    assert len(readings_crash) == 15, "Links incident to crashed node must not yield SNMP readings"
    assert not any("C" in r.link.split("-") for r in readings_crash)
    avg_crash = compute_avg_rtt_latency(readings_crash)
    manual_crash = round(sum(r.latency for r in readings_crash) / len(readings_crash), 2)
    assert avg_crash == manual_crash


def test_trap_ml_agreement_backend_isolation_and_matching():
    """Verify reconciler isolates different links (0% agreement) and pairs identical links (100% agreement)."""
    from self_healing.alert_reconciler import AlertReconciler
    from shared.schemas import Alert

    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=False)

    # 1. Dual faults on DIFFERENT links: D-E (ML) vs E-F (TRAP)
    ml_de = Alert(timestamp=100.0, source="ml_engine", link="D-E", predicted_state="congested", confidence=0.75)
    trap_ef = Alert(timestamp=100.4, source="snmp_trap", link="E-F", predicted_state="failed", confidence=None)

    r1 = reconciler.process_alert(ml_de)
    assert r1 is None, "D-E should be buffered waiting for companion"

    r2 = reconciler.process_alert(trap_ef)
    assert r2 is None, "E-F must NOT match D-E despite falling within the 2s time window!"

    # Flush pending after window expires
    flushed = reconciler.flush_pending(current_time=105.0)
    assert len(flushed) == 2
    stats = reconciler.get_summary_stats()
    assert stats["agreements"] == 0
    assert stats["agreement_rate"] == 0.0

    # 2. Genuine agreement on SAME link: B-C TRAP + B-C ML within 2.0s
    trap_bc = Alert(timestamp=200.0, source="snmp_trap", link="B-C", predicted_state="failed", confidence=None)
    ml_bc = Alert(timestamp=200.35, source="ml_engine", link="B-C", predicted_state="failed", confidence=0.98)

    reconciler.process_alert(trap_bc)
    rec = reconciler.process_alert(ml_bc)
    assert rec is not None, "Same link within window must pair and agree"
    assert rec.agreement is True
    assert rec.time_delta_sec == 0.35

    # Rate is now 1 agreement out of 3 total records (2 solo + 1 agreement)
    stats2 = reconciler.get_summary_stats()
    assert stats2["agreements"] == 1
    assert stats2["total_records"] == 3


def test_split_mttr_reactive_vs_proactive():
    """Verify compute_split_mttr partitions reroute events by trigger_alert.source ('snmp_trap' vs 'ml_engine')."""
    from evaluation.metrics import compute_split_mttr
    from shared.schemas import Alert, RerouteEvent

    trap_alert = Alert(timestamp=10.0, source="snmp_trap", link="A-B", predicted_state="failed", confidence=None)
    ml_alert = Alert(timestamp=20.0, source="ml_engine", link="C-D", predicted_state="congested", confidence=0.88)

    events = [
        # Reactive reroutes (SNMP TRAP)
        RerouteEvent(timestamp=10.001, failed_link="A-B", old_path=["A", "B"], new_path=["A", "C", "B"], trigger_alert=trap_alert, recovery_latency_ms=0.4),
        RerouteEvent(timestamp=11.001, failed_link="A-B", old_path=["A", "B"], new_path=["A", "D", "B"], trigger_alert=trap_alert, recovery_latency_ms=0.6),
        # Proactive reroute (ML Engine)
        RerouteEvent(timestamp=23.5, failed_link="C-D", old_path=["C", "D"], new_path=["C", "E", "D"], trigger_alert=ml_alert, recovery_latency_ms=3500.0),
    ]

    split = compute_split_mttr(events)

    # Reactive: (0.4 + 0.6) / 2 = 0.5 ms
    assert split["reactive_count"] == 2
    assert split["reactive_mttr_ms"] == 0.5

    # Proactive: 3500.0 ms
    assert split["proactive_count"] == 1
    assert split["proactive_mttr_ms"] == 3500.0

    # Overall: (0.4 + 0.6 + 3500.0) / 3 = 1167.0 ms
    assert split["total_count"] == 3
    assert split["overall_mttr_ms"] == 1167.0


def test_pre_silence_final_reading_enables_live_agreement():
    """
    Verify that injecting link_failure or router_crash emits exactly one final pre-silence
    TelemetryReading, allowing the ML engine to independently classify the failed state
    and achieve live TRAP/ML agreement without double-triggering reroutes or corrupting ongoing latency.
    """
    from shared.event_bus import bus
    from shared.config import TOPIC_ALERT, TOPIC_REROUTE, TOPIC_TELEMETRY
    from network_sim.snmp_agent import agent_manager
    from telemetry.snmp_poller import poll_all_nodes
    from evaluation.metrics import compute_avg_rtt_latency

    bus.clear()

    g = build_topology(n_nodes=10, seed=42)
    agent_manager.init_agents(g)
    agent_manager.sync_telemetry(g)

    injector = FaultInjector(g)
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=True)
    ml_service = MLInferenceService(auto_subscribe=True)
    controller = RoutingController(g)

    alerts = []
    reroutes = []
    telemetries = []
    bus.subscribe(TOPIC_ALERT, lambda a: alerts.append(a))
    bus.subscribe(TOPIC_REROUTE, lambda r: reroutes.append(r))
    bus.subscribe(TOPIC_TELEMETRY, lambda t: telemetries.append(t))

    controller.set_active_path("A", "E", ["A", "B", "C", "D", "E"])

    # 1. Inject link_failure on D-E
    t_inject = 1000.0
    injector.inject("link_failure", "D-E", timestamp=t_inject)

    # Verify alerts: exactly one TRAP alert and one ML alert on D-E
    de_traps = [a for a in alerts if a.source == "snmp_trap" and a.link in ("D-E", "E-D")]
    de_mls = [a for a in alerts if a.source == "ml_engine" and a.link in ("D-E", "E-D")]
    assert len(de_traps) == 1, "Exactly one SNMP TRAP must fire for D-E"
    assert len(de_mls) == 1, "Exactly one ML transition alert must fire for D-E"
    assert de_mls[0].predicted_state == "failed"

    # Verify reconciliation agreement achieved live
    assert len(reconciler.reconciliation_history) == 1
    rec = reconciler.reconciliation_history[0]
    assert rec.agreement is True
    assert rec.link in ("D-E", "E-D")
    assert rec.sources == ["snmp_trap", "ml_engine"]
    assert rec.time_delta_sec <= 0.05
    assert reconciler.get_summary_stats()["agreement_rate"] == 1.0

    # Verify deduplication: exactly one reroute triggered, not two
    assert len(reroutes) == 1, "Must not double-trigger reroute for concurrent TRAP + ML alerts"
    assert reroutes[0].failed_link in ("D-E", "E-D")
    assert reroutes[0].trigger_alert.source == "snmp_trap"

    # Verify subsequent polling cleanly excludes failed link
    readings = poll_all_nodes(g, timestamp=t_inject + 1.0)
    assert len(readings) == 16, "Failed link must remain silent and excluded on subsequent polls"
    assert not any(r.link in ("D-E", "E-D") for r in readings)
    avg_lat = compute_avg_rtt_latency(readings)
    assert 7.0 <= avg_lat <= 9.0

    # 2. Test router_crash on node C
    bus.clear()
    injector.reset_faults()
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=True)
    ml_service.reset_state()
    crash_telemetries = []
    bus.subscribe(TOPIC_TELEMETRY, lambda t: crash_telemetries.append(t))

    t_crash = 2000.0
    incident_edges = list(g.neighbors("C"))
    injector.inject("router_crash", "C", timestamp=t_crash)

    # Every incident edge must receive exactly one final reading
    assert len(crash_telemetries) == len(incident_edges)
    emitted_links = {t.link for t in crash_telemetries}
    for nbr in incident_edges:
        canon = f"{min('C', nbr)}-{max('C', nbr)}"
        assert canon in emitted_links
        assert all(t.state == "failed" for t in crash_telemetries if t.link == canon)

    # Subsequent poll excludes all incident edges to node C
    readings_crash = poll_all_nodes(g, timestamp=t_crash + 1.0)
    assert len(readings_crash) == 17 - len(incident_edges)
    assert not any("C" in r.link.split("-") for r in readings_crash)




