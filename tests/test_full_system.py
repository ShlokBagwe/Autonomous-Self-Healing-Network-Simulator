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
