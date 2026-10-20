import sys, os
sys.path.insert(0, os.path.abspath("."))
import networkx as nx
from network_sim.topology import build_topology
from network_sim.fault_injector import FaultInjector
from self_healing.routing_controller import RoutingController, recalculate_route
from telemetry.snmp_poller import poll_all_nodes
from shared.event_bus import bus

def test_degradation_after_reroute():
    g = build_topology()
    ctrl = RoutingController(g)
    inj = FaultInjector(g)

    # Initial route carrying traffic over D-E
    init_path = ["A", "D", "E"]
    ctrl.set_active_path("A", "E", init_path)
    print("Initial active path:", init_path)
    assert ("D", "E") in zip(init_path[:-1], init_path[1:]), "D-E must be in initial path"

    # Degrade D-E
    res = inj.inject("degradation", "D-E")
    print(f"Fault injected: kind={res['kind']} on target={res['target']}")

    # First poll cycle: D-E is still in initial active path
    readings1 = poll_all_nodes(g, 100.0)
    de_reading1 = next(r for r in readings1 if r.link in ("D-E", "E-D"))
    print(f"Poll 1 [ON active path]: D-E latency = {de_reading1.latency:.2f} ms (status={g['D']['E']['status']})")

    # Controller recalculates route away from degraded D-E
    new_path = recalculate_route(g, "A", "E", failed_element="D-E", severity=0.7)
    ctrl.set_active_path("A", "E", new_path)
    print(f"Rerouted active path: {new_path}")
    active_edges = list(zip(new_path[:-1], new_path[1:]))
    assert ("D", "E") not in active_edges and ("E", "D") not in active_edges, "D-E should NOT be on new active path!"

    # Subsequent poll cycles: D-E is NOT on active path, but MUST keep degrading in the background
    print("\nSubsequent poll cycles (D-E is NOT in active path):")
    for cycle in range(2, 7):
        readings = poll_all_nodes(g, 100.0 + cycle)
        de_reading = next(r for r in readings if r.link in ("D-E", "E-D"))
        print(f"Poll {cycle} [OFF active path]: D-E latency = {de_reading.latency:.2f} ms | edge data latency = {g['D']['E']['latency']:.2f} ms")

if __name__ == "__main__":
    test_degradation_after_reroute()
