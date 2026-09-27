"""
Traffic simulation module for Member 1.
Generates packet flows across the network, tracks end-to-end latency and packet delivery ratio (PDR).
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.1 and Plan_docs/member-1-network-sim.md.
"""
import random
from typing import Dict, List, Optional, Tuple
import networkx as nx

from self_healing.routing_controller import recalculate_route


class TrafficSimulator:
    """Simulates continuous and discrete packet flows across the topology."""

    def __init__(self, graph: nx.Graph):
        self.graph = graph
        self.packets_sent = 0
        self.packets_delivered = 0
        self.packets_dropped = 0
        self.latencies: List[float] = []

    def set_graph(self, graph: nx.Graph) -> None:
        self.graph = graph

    def send_packet(
        self,
        src: str,
        dst: str,
        active_path: Optional[List[str]] = None,
        use_static_routing: bool = False,
    ) -> Tuple[bool, float]:
        """
        Send a packet from src to dst.
        If use_static_routing is True: path is determined by static shortest path without dynamic penalties.
        If active_path is provided: follows active_path.
        Returns: (delivered: bool, end_to_end_latency_ms: float)
        """
        self.packets_sent += 1

        if src not in self.graph or dst not in self.graph:
            self.packets_dropped += 1
            return False, 0.0

        # Determine path
        if active_path:
            path = active_path
        elif use_static_routing:
            try:
                # Static shortest path only relies on base_cost
                path = nx.dijkstra_path(self.graph, src, dst, weight=lambda u, v, d: float(d.get("base_cost", 1.0)))
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self.packets_dropped += 1
                return False, 0.0
        else:
            try:
                path = recalculate_route(self.graph, src, dst)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self.packets_dropped += 1
                return False, 0.0

        total_latency = 0.0
        # Traverse path links
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            if not self.graph.has_edge(u, v):
                self.packets_dropped += 1
                return False, 0.0

            edge_data = self.graph.edges[u, v]
            if edge_data.get("ifOperStatus", 1) == 2 or edge_data.get("failure_risk", 0.0) >= 0.9:
                # Link is down -> packet drop
                self.packets_dropped += 1
                return False, 0.0

            loss_prob = float(edge_data.get("packet_loss", 0.0)) / 100.0
            if random.random() < loss_prob:
                self.packets_dropped += 1
                return False, 0.0

            total_latency += float(edge_data.get("latency", 5.0))

        self.packets_delivered += 1
        self.latencies.append(total_latency)
        return True, round(total_latency, 2)

    def get_pdr(self) -> float:
        """Calculate Packet Delivery Ratio (PDR = successful_packets / total_packets)."""
        if self.packets_sent == 0:
            return 1.0
        return round(self.packets_delivered / self.packets_sent, 4)

    def get_avg_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return round(sum(self.latencies) / len(self.latencies), 2)

    def reset_stats(self) -> None:
        self.packets_sent = 0
        self.packets_delivered = 0
        self.packets_dropped = 0
        self.latencies.clear()
