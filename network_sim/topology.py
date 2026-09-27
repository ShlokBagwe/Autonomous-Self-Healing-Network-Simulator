"""
Topology generation module for Member 1.
Constructs connected 8-12 node virtual network topologies with telemetry attributes and base costs.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.1 and Plan_docs/member-1-network-sim.md.
"""
import random
from typing import Dict, List, Optional, Tuple
import networkx as nx

from shared.config import (
    DEFAULT_NODE_COUNT,
    PENALTY_WEIGHT_CONGESTION,
    PENALTY_WEIGHT_FAILURE_RISK,
    PENALTY_WEIGHT_LATENCY,
    PENALTY_WEIGHT_LOSS,
)

NODE_LABELS = [chr(ord("A") + i) for i in range(26)]


def calculate_edge_cost(
    u: str,
    v: str,
    edge_data: Dict,
    failed_element: Optional[str] = None,
    severity: float = 1.0,
) -> float:
    """
    Edge cost formula matching Master Section 6.1:
    cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty
    """
    base_cost = float(edge_data.get("base_cost", 1.0))
    latency = float(edge_data.get("latency", 5.0))
    loss = float(edge_data.get("packet_loss", 0.0))
    congestion = float(edge_data.get("congestion_level", edge_data.get("utilization", 0.0)))
    failure_risk = float(edge_data.get("failure_risk", 0.0))

    cost = (
        base_cost
        + (latency * PENALTY_WEIGHT_LATENCY)
        + (loss * PENALTY_WEIGHT_LOSS)
        + (congestion * PENALTY_WEIGHT_CONGESTION)
        + (failure_risk * PENALTY_WEIGHT_FAILURE_RISK)
    )

    # Hard failure check: failed links cannot carry traffic
    if edge_data.get("ifOperStatus") == 2 or edge_data.get("status") == "failed" or edge_data.get("packet_loss", 0.0) >= 100.0:
        return 1e9

    if failed_element:
        if failed_element == f"{u}-{v}" or failed_element == f"{v}-{u}":
            return 1e9
        elif failed_element in (u, v):
            return 1e9

    return float(cost)


def build_topology(n_nodes: int = DEFAULT_NODE_COUNT, seed: Optional[int] = None) -> nx.Graph:
    """
    Build a connected network topology with 8 to 12 nodes.
    Each edge is initialized with healthy baseline telemetry attributes:
    base_cost, latency, jitter, packet_loss, queue, throughput, utilization, ifOperStatus.
    """
    if seed is not None:
        random.seed(seed)

    n_nodes = max(8, min(12, n_nodes))
    nodes = NODE_LABELS[:n_nodes]

    # Create connected backbone ring + cross links for path diversity
    g = nx.Graph()
    for node in nodes:
        g.add_node(node, status="up")

    # Add cycle backbone
    for i in range(n_nodes):
        u = nodes[i]
        v = nodes[(i + 1) % n_nodes]
        g.add_edge(u, v)

    # Add chords/cross-links for alternative routing paths
    rng = random.Random(seed if seed is not None else 42)
    potential_edges = []
    for i in range(n_nodes):
        for j in range(i + 2, n_nodes):
            if (i, j) != (0, n_nodes - 1):
                potential_edges.append((nodes[i], nodes[j]))

    rng.shuffle(potential_edges)
    num_chords = min(len(potential_edges), n_nodes // 2 + 2)
    for k in range(num_chords):
        u, v = potential_edges[k]
        g.add_edge(u, v)

    # Assign realistic telemetry attributes to all edges
    for u, v in g.edges():
        base_latency = round(rng.uniform(4.0, 12.0), 2)
        base_jitter = round(rng.uniform(0.5, 2.0), 2)
        base_throughput = round(rng.uniform(85.0, 100.0), 2)
        base_utilization = round(rng.uniform(0.15, 0.40), 2)
        g.edges[u, v].update({
            "base_cost": 1.0,
            "base_latency": base_latency,
            "latency": base_latency,
            "base_jitter": base_jitter,
            "jitter": base_jitter,
            "packet_loss": 0.0,
            "queue": rng.randint(0, 3),
            "base_throughput": base_throughput,
            "throughput": base_throughput,
            "base_utilization": base_utilization,
            "utilization": base_utilization,
            "congestion_level": 0.0,
            "failure_risk": 0.0,
            "ifOperStatus": 1,  # 1 = up, 2 = down
            "ifInErrors": 0,
            "status": "healthy",
        })

    return g
