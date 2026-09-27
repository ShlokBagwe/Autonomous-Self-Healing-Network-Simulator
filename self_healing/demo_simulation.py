"""
Member 3 Interactive Demo / Simulation Harness.
Simulates fault scenarios, feeds alerts to AlertReconciler and RoutingController,
and prints live diagnosis, dynamic Dijkstra rerouting, and TRAP vs ML reconciliation.
"""
import time
import networkx as nx

from shared.event_bus import bus
from shared.schemas import Alert
from shared.config import TOPIC_ALERT, TOPIC_FAULT, TOPIC_REROUTE
from self_healing.alert_reconciler import AlertReconciler
from self_healing.diagnosis import diagnose
from self_healing.routing_controller import RoutingController


def create_demo_network() -> nx.Graph:
    """Build a sample 8-node network topology."""
    g = nx.Graph()
    # Topology:
    #   A --- B --- C --- D
    #   |     |     |     |
    #   E --- F --- G --- H
    links = [
        ("A", "B", 10.0), ("B", "C", 10.0), ("C", "D", 10.0),
        ("E", "F", 10.0), ("F", "G", 10.0), ("G", "H", 10.0),
        ("A", "E", 15.0), ("B", "F", 15.0), ("C", "G", 15.0), ("D", "H", 15.0),
    ]
    for u, v, latency in links:
        g.add_edge(u, v, base_cost=1.0, latency=latency, packet_loss=0.0, congestion_level=0.0, failure_risk=0.0)
    return g


def run_demo():
    print("=" * 65)
    print("  Autonomous Self-Healing Network Simulator - Member 3 Demo")
    print("=" * 65)

    g = create_demo_network()
    reconciler = AlertReconciler(window_sec=2.0)
    controller = RoutingController(g)

    # Establish initial active path from A to D
    initial_path = ["A", "B", "C", "D"]
    controller.set_active_path("A", "D", initial_path)
    print(f"\n[1] Initial Active Route (A -> D): {' -> '.join(initial_path)}")

    # 1. Fault Scenario: Link Failure on B-C
    print("\n[2] Injected Fault: Link Failure on 'B-C'...")
    t_fault = time.time()
    bus.publish(TOPIC_FAULT, {"target": "B-C", "timestamp": t_fault, "kind": "link_failure"})

    # Proactive ML Engine Alert arrives first (e.g. progressive degradation detected)
    t_ml = t_fault + 0.12
    ml_alert = Alert(timestamp=t_ml, source="ml_engine", link="B-C", predicted_state="failed", confidence=0.98)
    print(f" -> [ML Engine Alert] Timestamp: {t_ml:.2f} | Link: B-C | Confidence: 98%")
    bus.publish(TOPIC_ALERT, ml_alert)

    # Reactive SNMP TRAP arrives shortly after
    t_trap = t_fault + 0.28
    trap_alert = Alert(timestamp=t_trap, source="snmp_trap", link="B-C", predicted_state="failed")
    print(f" -> [SNMP TRAP Alert] Timestamp: {t_trap:.2f} | Link: B-C | Agent Unreachable")
    bus.publish(TOPIC_ALERT, trap_alert)

    # Flush pending reconciler records
    reconciler.flush_pending(current_time=time.time() + 5.0)

    # View healed path
    healed_path = controller.active_paths[("A", "D")]
    print(f"\n[3] Dynamic Dijkstra Recalculated Path: {' -> '.join(healed_path)}")

    # View reconciliation statistics
    stats = reconciler.get_summary_stats()
    print("\n[4] Reconciler Summary:")
    for k, v in stats.items():
        print(f"    - {k}: {v}")

    print("\n" + "=" * 65)
    print("  Demo completed successfully! Events saved to logs/events.jsonl")
    print("=" * 65)


if __name__ == "__main__":
    run_demo()
