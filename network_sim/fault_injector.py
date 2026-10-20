"""
Fault Injector module for Member 1.
Implements the 5 canonical fault scenarios: link_failure, router_crash, congestion, degradation, multi_fault.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.2, 7 and Plan_docs/member-1-network-sim.md.
"""
import logging
import time
from typing import Dict, List, Literal, Optional, Tuple, Union
import networkx as nx

from shared.config import TOPIC_FAULT, TOPIC_TELEMETRY
from shared.event_bus import bus
from shared.schemas import TelemetryReading
from network_sim.snmp_agent import agent_manager

logger = logging.getLogger("fault_injector")

FaultKind = Literal["link_failure", "router_crash", "congestion", "degradation", "multi_fault"]


def _resolve_link_nodes(target: str) -> Optional[Tuple[str, str]]:
    if "-" in target:
        parts = target.split("-", 1)
        return parts[0].strip(), parts[1].strip()
    return None


class FaultInjector:
    def __init__(self, graph: Optional[nx.Graph] = None):
        self.graph = graph
        self.injected_faults: List[Dict] = []

    def set_graph(self, graph: nx.Graph) -> None:
        self.graph = graph

    def inject(
        self,
        kind: FaultKind,
        target: Union[str, List[str]],
        timestamp: Optional[float] = None,
    ) -> Dict:
        """
        Inject a simulated fault into the graph, record t_fault_onset,
        fire reactive SNMP TRAP when appropriate, emit one final pre-silence
        TelemetryReading for ML classification, and publish 'fault.injected'.
        """
        if timestamp is None:
            timestamp = float(time.time())

        if self.graph is None:
            raise ValueError("Graph not set on FaultInjector.")

        payload = {
            "timestamp": timestamp,
            "kind": kind,
            "target": target,
        }

        # 1. Apply mutations to topology
        if kind == "link_failure":
            link_str = str(target)
            endpoints = _resolve_link_nodes(link_str)
            base_lat = 8.0
            if endpoints and self.graph.has_edge(*endpoints):
                u, v = endpoints
                base_lat = float(self.graph.edges[u, v].get("base_latency", self.graph.edges[u, v].get("latency", 8.0)))
                self.graph.edges[u, v].update({
                    "failure_risk": 1.0,
                    "packet_loss": 100.0,
                    "throughput": 0.0,
                    "ifOperStatus": 2,  # down
                    "status": "failed",
                })
            # Reactive TRAP fires immediately on hard failure
            agent_manager.fire_trap(link_str, timestamp=timestamp)

            # Emit exactly one final pre-silence TelemetryReading before agent goes silent
            if endpoints and self.graph.has_edge(*endpoints):
                u, v = endpoints
                canon_link = f"{min(u, v)}-{max(u, v)}"
                final_reading = TelemetryReading(
                    timestamp=round(timestamp, 3),
                    link=canon_link,
                    latency=round(base_lat + 342.0, 2),  # ~350ms, matching ML failed distribution
                    jitter=45.0,
                    packet_loss=100.0,
                    queue=0.0,
                    throughput=0.0,
                    utilization=0.0,
                    state="failed",
                )
                bus.publish(TOPIC_TELEMETRY, final_reading)

        elif kind == "router_crash":
            node_str = str(target)
            affected_edges = []
            if self.graph.has_node(node_str):
                self.graph.nodes[node_str]["status"] = "down"
                for neighbor in sorted(list(self.graph.neighbors(node_str))):
                    base_lat = float(self.graph.edges[node_str, neighbor].get("base_latency", self.graph.edges[node_str, neighbor].get("latency", 8.0)))
                    affected_edges.append((node_str, neighbor, base_lat))
                    self.graph.edges[node_str, neighbor].update({
                        "failure_risk": 1.0,
                        "packet_loss": 100.0,
                        "throughput": 0.0,
                        "ifOperStatus": 2,
                        "status": "failed",
                    })
            agent_manager.fire_trap(node_str, timestamp=timestamp)

            # Emit exactly one final pre-silence TelemetryReading for each incident edge
            for u, v, base_lat in affected_edges:
                canon_link = f"{min(u, v)}-{max(u, v)}"
                final_reading = TelemetryReading(
                    timestamp=round(timestamp, 3),
                    link=canon_link,
                    latency=round(base_lat + 342.0, 2),
                    jitter=45.0,
                    packet_loss=100.0,
                    queue=0.0,
                    throughput=0.0,
                    utilization=0.0,
                    state="failed",
                )
                bus.publish(TOPIC_TELEMETRY, final_reading)

        elif kind == "congestion":
            link_str = str(target)
            endpoints = _resolve_link_nodes(link_str)
            if endpoints and self.graph.has_edge(*endpoints):
                u, v = endpoints
                self.graph.edges[u, v].update({
                    "congestion_level": 0.95,
                    "utilization": 0.96,
                    "queue": 85,
                    "latency": 120.0,
                    "jitter": 28.5,
                    "packet_loss": 12.0,
                    "throughput": 15.0,
                    "status": "congested",
                })
            # Congestion is detected proactively via polling / ML inference, not TRAP

        elif kind == "degradation":
            link_str = str(target)
            endpoints = _resolve_link_nodes(link_str)
            if endpoints and self.graph.has_edge(*endpoints):
                u, v = endpoints
                base_lat = float(self.graph.edges[u, v].get("base_latency", self.graph.edges[u, v].get("latency", 8.0)))
                # Initial onset values: mild degradation, which worsens progressively on each subsequent poll tick
                self.graph.edges[u, v].update({
                    "congestion_level": 0.15,
                    "utilization": 0.40,
                    "queue": 5.0,
                    "latency": round(base_lat + 4.0, 2),
                    "jitter": 2.5,
                    "packet_loss": 0.5,
                    "throughput": 85.0,
                    "status": "degrading",
                })

        elif kind == "multi_fault":
            targets = target if isinstance(target, list) else [str(target)]
            for sub_target in targets:
                endpoints = _resolve_link_nodes(sub_target)
                if endpoints and self.graph.has_edge(*endpoints):
                    u, v = endpoints
                    base_lat = float(self.graph.edges[u, v].get("base_latency", self.graph.edges[u, v].get("latency", 8.0)))
                    self.graph.edges[u, v].update({
                        "failure_risk": 1.0,
                        "packet_loss": 100.0,
                        "throughput": 0.0,
                        "ifOperStatus": 2,
                        "status": "failed",
                    })
                    agent_manager.fire_trap(sub_target, timestamp=timestamp)
                    canon_link = f"{min(u, v)}-{max(u, v)}"
                    final_reading = TelemetryReading(
                        timestamp=round(timestamp, 3),
                        link=canon_link,
                        latency=round(base_lat + 342.0, 2),
                        jitter=45.0,
                        packet_loss=100.0,
                        queue=0.0,
                        throughput=0.0,
                        utilization=0.0,
                        state="failed",
                    )
                    bus.publish(TOPIC_TELEMETRY, final_reading)
                elif self.graph.has_node(sub_target):
                    node_str = sub_target
                    affected_edges = []
                    self.graph.nodes[node_str]["status"] = "down"
                    for neighbor in sorted(list(self.graph.neighbors(node_str))):
                        base_lat = float(self.graph.edges[node_str, neighbor].get("base_latency", self.graph.edges[node_str, neighbor].get("latency", 8.0)))
                        affected_edges.append((node_str, neighbor, base_lat))
                        self.graph.edges[node_str, neighbor].update({
                            "failure_risk": 1.0,
                            "packet_loss": 100.0,
                            "throughput": 0.0,
                            "ifOperStatus": 2,
                            "status": "failed",
                        })
                    agent_manager.fire_trap(node_str, timestamp=timestamp)
                    for u, v, base_lat in affected_edges:
                        canon_link = f"{min(u, v)}-{max(u, v)}"
                        final_reading = TelemetryReading(
                            timestamp=round(timestamp, 3),
                            link=canon_link,
                            latency=round(base_lat + 342.0, 2),
                            jitter=45.0,
                            packet_loss=100.0,
                            queue=0.0,
                            throughput=0.0,
                            utilization=0.0,
                            state="failed",
                        )
                        bus.publish(TOPIC_TELEMETRY, final_reading)

        # 2. Sync to SNMP agent MIB tables
        agent_manager.sync_telemetry(self.graph)

        # 3. Publish fault onset event
        self.injected_faults.append(payload)
        bus.publish(TOPIC_FAULT, payload)
        logger.info(f"Fault injected: {kind} on {target} at t={timestamp:.2f}")
        return payload

    def reset_faults(self) -> None:
        """Restore all links and nodes in graph to healthy state."""
        if self.graph is None:
            return
        for node in self.graph.nodes():
            self.graph.nodes[node]["status"] = "up"
        for u, v in self.graph.edges():
            edge = self.graph.edges[u, v]
            base_lat = edge.get("base_latency", edge.get("latency", 8.0))
            base_jit = edge.get("base_jitter", edge.get("jitter", 1.0))
            base_tp = edge.get("base_throughput", edge.get("throughput", 95.0))
            base_util = edge.get("base_utilization", edge.get("utilization", 0.25))
            edge.update({
                "failure_risk": 0.0,
                "congestion_level": 0.0,
                "packet_loss": 0.0,
                "queue": 1,
                "latency": round(float(base_lat), 2),
                "jitter": round(float(base_jit), 2),
                "throughput": round(float(base_tp), 2),
                "utilization": round(float(base_util), 2),
                "ifOperStatus": 1,
                "status": "healthy",
            })
        agent_manager.sync_telemetry(self.graph)


# Convenience function matching Master Section 6.2
def inject_fault(graph: nx.Graph, kind: FaultKind, target: Union[str, List[str]]) -> None:
    injector = FaultInjector(graph)
    injector.inject(kind, target)
