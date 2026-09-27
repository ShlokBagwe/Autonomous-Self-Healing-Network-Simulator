"""
Unit and Integration tests for Member 3: Self-Healing, Diagnosis, Routing Controller, and Reconciler.
"""
import json
import os
import time
import networkx as nx
import pytest

from shared.config import EVENTS_LOG_FILE, RECONCILE_WINDOW_SEC, TOPIC_ALERT, TOPIC_FAULT, TOPIC_REROUTE
from shared.event_bus import bus
from shared.schemas import Alert, RerouteEvent, ReconciliationRecord, TelemetryReading
from self_healing.alert_reconciler import AlertReconciler
from self_healing.diagnosis import diagnose, DiagnosisResult, calculate_severity, parse_element
from self_healing.routing_controller import (
    RoutingController,
    recalculate_route,
    calculate_edge_cost,
    normalize_link_name,
)


@pytest.fixture(autouse=True)
def clean_event_bus():
    """Ensure event bus is cleared before and after each test."""
    bus.clear()
    yield
    bus.clear()


@pytest.fixture
def sample_topology() -> nx.Graph:
    """
    Build a standard 6-node test graph:
    A - B - C
    |       |
    D - E - F
    """
    g = nx.Graph()
    edges = [
        ("A", "B", {"base_cost": 1.0, "latency": 5.0, "packet_loss": 0.0}),
        ("B", "C", {"base_cost": 1.0, "latency": 5.0, "packet_loss": 0.0}),
        ("A", "D", {"base_cost": 2.0, "latency": 10.0, "packet_loss": 0.0}),
        ("D", "E", {"base_cost": 2.0, "latency": 10.0, "packet_loss": 0.0}),
        ("E", "F", {"base_cost": 2.0, "latency": 10.0, "packet_loss": 0.0}),
        ("C", "F", {"base_cost": 2.0, "latency": 10.0, "packet_loss": 0.0}),
    ]
    for u, v, data in edges:
        g.add_edge(u, v, **data)
    return g


def test_shared_schemas():
    """Test schema dataclass instantiation and type compliance."""
    reading = TelemetryReading(
        timestamp=10.0,
        link="A-B",
        latency=15.2,
        jitter=1.1,
        packet_loss=0.0,
        queue=2,
        throughput=95.0,
        utilization=0.4,
        state="healthy",
    )
    assert reading.link == "A-B"
    assert reading.state == "healthy"

    alert = Alert(
        timestamp=12.0,
        source="snmp_trap",
        link="A-B",
        predicted_state="failed",
        confidence=None,
    )
    assert alert.source == "snmp_trap"
    assert alert.confidence is None


def test_diagnosis_link_and_node():
    """Test parse_element and diagnose function."""
    is_link, endpoints = parse_element("A-B")
    assert is_link is True
    assert endpoints == ("A", "B")

    is_link_node, endpoints_node = parse_element("C")
    assert is_link_node is False
    assert endpoints_node is None

    # SNMP TRAP Alert diagnosis (maximum severity 1.0)
    trap_alert = Alert(
        timestamp=10.0,
        source="snmp_trap",
        link="B-C",
        predicted_state="failed",
    )
    element, severity = diagnose(trap_alert)
    assert element == "B-C"
    assert severity == 1.0

    # ML Alert diagnosis for congestion
    ml_congested = Alert(
        timestamp=11.0,
        source="ml_engine",
        link="A-B",
        predicted_state="congested",
        confidence=0.8,
    )
    element_ml, severity_ml = diagnose(ml_congested)
    assert element_ml == "A-B"
    assert 0.3 <= severity_ml <= 0.7

    # ML Alert diagnosis for failure
    ml_failed = Alert(
        timestamp=12.0,
        source="ml_engine",
        link="A-B",
        predicted_state="failed",
        confidence=0.9,
    )
    diag = diagnose(ml_failed)
    assert isinstance(diag, DiagnosisResult)
    assert diag.severity >= 0.8


def test_dynamic_edge_cost_and_dijkstra(sample_topology):
    """Test Dijkstra shortest path recalculation with dynamic edge penalties."""
    # Under healthy conditions, shortest path A -> C is A -> B -> C (cost: 1 + 1 = 2)
    path = recalculate_route(sample_topology, source="A", dest="C")
    assert path == ["A", "B", "C"]

    # When link B-C fails, Dijkstra must reroute via A -> D -> E -> F -> C
    path_rerouted = recalculate_route(
        sample_topology,
        source="A",
        dest="C",
        failed_element="B-C",
        severity=1.0,
    )
    assert path_rerouted == ["A", "D", "E", "F", "C"]

    # When node B crashes, Dijkstra must avoid B completely
    path_node_crash = recalculate_route(
        sample_topology,
        source="A",
        dest="C",
        failed_element="B",
        severity=1.0,
    )
    assert "B" not in path_node_crash
    assert path_node_crash == ["A", "D", "E", "F", "C"]


def test_routing_controller_end_to_end(sample_topology):
    """Test RoutingController event handling and RerouteEvent generation."""
    controller = RoutingController(sample_topology)
    controller.set_active_path("A", "C", ["A", "B", "C"])

    # Simulate fault onset at timestamp 100.0
    bus.publish(TOPIC_FAULT, {"target": "B-C", "timestamp": 100.0, "kind": "link_failure"})

    received_events = []
    bus.subscribe(TOPIC_REROUTE, lambda ev: received_events.append(ev))

    # Alert arrives at 100.4
    alert = Alert(
        timestamp=100.4,
        source="snmp_trap",
        link="B-C",
        predicted_state="failed",
    )
    bus.publish(TOPIC_ALERT, alert)

    assert len(received_events) == 1
    event = received_events[0]
    assert event.failed_link == "B-C"
    assert event.old_path == ["A", "B", "C"]
    assert event.new_path == ["A", "D", "E", "F", "C"]
    assert event.recovery_latency_ms >= 0.0


def test_alert_reconciler_agreement():
    """Test AlertReconciler pairing SNMP TRAP and ML alerts for same link."""
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=False)

    trap_alert = Alert(
        timestamp=50.0,
        source="snmp_trap",
        link="A-B",
        predicted_state="failed",
    )
    ml_alert = Alert(
        timestamp=50.35,
        source="ml_engine",
        link="A-B",
        predicted_state="failed",
        confidence=0.96,
    )

    # 1. Feed TRAP alert
    rec1 = reconciler.process_alert(trap_alert)
    assert rec1 is None  # Waiting for possible companion

    # 2. Feed ML alert within window (delta = 0.35s)
    rec2 = reconciler.process_alert(ml_alert)
    assert rec2 is not None
    assert rec2.agreement is True
    assert rec2.link == "A-B"
    assert rec2.trap_timestamp == 50.0
    assert rec2.ml_timestamp == 50.35
    assert rec2.time_delta_sec == 0.35
    assert rec2.ml_confidence == 0.96

    stats = reconciler.get_summary_stats()
    assert stats["agreements"] == 1
    assert stats["agreement_rate"] == 1.0


def test_alert_reconciler_single_source_timeout():
    """Test AlertReconciler flushing alerts that do not receive companion within window."""
    reconciler = AlertReconciler(window_sec=2.0, auto_subscribe=False)

    solo_trap = Alert(
        timestamp=10.0,
        source="snmp_trap",
        link="C-D",
        predicted_state="failed",
    )
    reconciler.process_alert(solo_trap)

    # Flush at timestamp 11.0 (window not expired yet)
    flushed = reconciler.flush_pending(current_time=11.0)
    assert len(flushed) == 0

    # Flush at timestamp 12.5 (window expired: 12.5 - 10.0 = 2.5 > 2.0)
    flushed = reconciler.flush_pending(current_time=12.5)
    assert len(flushed) == 1
    record = flushed[0]
    assert record.agreement is False
    assert record.sources == ["snmp_trap"]
    assert record.trap_timestamp == 10.0
    assert record.ml_timestamp is None


def test_events_jsonl_output():
    """Verify events are correctly appended in JSON Lines format."""
    assert os.path.exists(EVENTS_LOG_FILE)
    with open(EVENTS_LOG_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    # Ensure valid json on all written lines
    for line in lines:
        parsed = json.loads(line)
        assert "type" in parsed
        assert "payload" in parsed


def test_routing_controller_unreachable_destination(sample_topology):
    """Verify that when network is partitioned and destination is unreachable, controller emits RerouteEvent with empty new_path."""
    controller = RoutingController(sample_topology)
    controller.set_active_path("A", "C", ["A", "B", "C"])

    # Fail link B-C and alternative path links so C is completely unreachable
    sample_topology.edges["B", "C"]["status"] = "failed"
    sample_topology.edges["B", "C"]["ifOperStatus"] = 2
    sample_topology.edges["F", "C"]["status"] = "failed"
    sample_topology.edges["F", "C"]["ifOperStatus"] = 2

    received_events = []
    bus.subscribe(TOPIC_REROUTE, lambda ev: received_events.append(ev))

    alert = Alert(
        timestamp=200.0,
        source="snmp_trap",
        link="B-C",
        predicted_state="failed",
    )
    event = controller.heal_path("A", "C", alert)

    assert event is not None
    assert event.new_path == []
    assert controller.active_paths[("A", "C")] == []
    assert len(received_events) >= 1
    assert received_events[-1].new_path == []


def test_routing_controller_congested_edges_remain_traversable(sample_topology):
    """Verify that when both incoming edges to a destination are congested, Dijkstra STILL routes through them at higher cost instead of declaring unreachable."""
    controller = RoutingController(sample_topology)
    controller.set_active_path("A", "C", ["A", "B", "C"])

    # Node C is connected only to B and F in sample_topology.
    # Mark both B-C and F-C as CONGESTED (not failed)
    sample_topology.edges["B", "C"].update({
        "congestion_level": 0.95,
        "latency": 120.0,
        "packet_loss": 12.0,
        "status": "congested",
        "ifOperStatus": 1,
    })
    sample_topology.edges["F", "C"].update({
        "congestion_level": 0.95,
        "latency": 125.0,
        "packet_loss": 14.0,
        "status": "congested",
        "ifOperStatus": 1,
    })

    congestion_alert = Alert(
        timestamp=300.0,
        source="ml_engine",
        link="B-C",
        predicted_state="congested",
        confidence=0.85,
    )
    event = controller.heal_path("A", "C", congestion_alert)

    assert event is not None
    # Must STILL find a path to C — congestion degrades cost, but does not partition the network
    assert len(event.new_path) > 1
    assert event.new_path[-1] == "C"
    assert event.new_path[0] == "A"
    assert controller.active_paths[("A", "C")] == event.new_path


