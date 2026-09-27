"""
SNMP Agent Simulation for Member 1.
Simulates per-node SNMP agents exposing standard MIB / custom enterprise OIDs (1.3.6.1.4.1.9999.1.x)
over localhost and generating reactive SNMP TRAPs upon fault occurrence.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 4.2 & 6.3.
"""
import logging
import time
from typing import Any, Dict, List, Optional
import networkx as nx

from shared.config import OID_BASE, OID_MAP, TOPIC_ALERT
from shared.event_bus import bus
from shared.schemas import Alert

logger = logging.getLogger("snmp_agent")


class SNMPAgent:
    """Simulated SNMP Agent running for a single network node."""

    def __init__(self, node_id: str, port: int):
        self.node_id = node_id
        self.port = port
        self.mib_table: Dict[str, Any] = {}

    def update_mib_from_edge(self, edge_data: Dict[str, Any]) -> None:
        """Update MIB scalar/table entries according to OID_MAP."""
        self.mib_table[f"{OID_BASE}.1"] = float(edge_data.get("latency", 5.0))
        self.mib_table[f"{OID_BASE}.2"] = float(edge_data.get("jitter", 1.0))
        self.mib_table[f"{OID_BASE}.3"] = float(edge_data.get("packet_loss", 0.0))
        self.mib_table[f"{OID_BASE}.4"] = int(edge_data.get("queue", 0))
        self.mib_table[f"{OID_BASE}.5"] = float(edge_data.get("throughput", 100.0))
        self.mib_table[f"{OID_BASE}.6"] = float(edge_data.get("utilization", 0.2))
        self.mib_table[f"{OID_BASE}.7"] = int(edge_data.get("ifOperStatus", 1))
        self.mib_table[f"{OID_BASE}.8"] = int(edge_data.get("ifInErrors", 0))

    def get(self, oid: str) -> Any:
        return self.mib_table.get(oid, None)

    def get_bulk(self, oids: List[str]) -> Dict[str, Any]:
        return {oid: self.mib_table.get(oid) for oid in oids if oid in self.mib_table}


class SNMPAgentManager:
    """Manages SNMP agents across all nodes in the topology."""

    def __init__(self, graph: Optional[nx.Graph] = None, base_port: int = 16100):
        self.base_port = base_port
        self.agents: Dict[str, SNMPAgent] = {}
        if graph:
            self.init_agents(graph)

    def init_agents(self, graph: nx.Graph) -> None:
        """Instantiate SNMP agents for every node in the graph."""
        self.agents.clear()
        for idx, node in enumerate(sorted(graph.nodes())):
            port = self.base_port + idx + 1
            self.agents[node] = SNMPAgent(node_id=node, port=port)

    def sync_telemetry(self, graph: nx.Graph) -> None:
        """Synchronize telemetry metrics from network graph to node SNMP MIBs."""
        for u, v, data in graph.edges(data=True):
            if u in self.agents:
                self.agents[u].update_mib_from_edge(data)
            if v in self.agents:
                self.agents[v].update_mib_from_edge(data)

    def fire_trap(self, target: str, timestamp: Optional[float] = None) -> Alert:
        """
        Send an immediate SNMP TRAP for a failed node or link.
        Publishes Alert(source='snmp_trap', ...) to 'alert.raised'.
        """
        if timestamp is None:
            timestamp = time.time()

        trap_alert = Alert(
            timestamp=timestamp,
            source="snmp_trap",
            link=target,
            predicted_state="failed",
            confidence=None,  # TRAPs have no ML confidence score
        )
        logger.info(f"SNMP TRAP fired for target '{target}' at {timestamp:.2f}")
        bus.publish(TOPIC_ALERT, trap_alert)
        return trap_alert


# Global singleton agent manager for in-process access
agent_manager = SNMPAgentManager()
