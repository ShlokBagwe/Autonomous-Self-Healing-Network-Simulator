"""
SNMP Poller for Member 1.
Periodically queries node telemetry metrics via SNMP GET/GETBULK simulation every POLL_INTERVAL_SEC,
packages them into TelemetryReading dataclasses, and publishes to 'telemetry.reading'.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.3 and Plan_docs/member-1-network-sim.md.
"""
import logging
import time
from typing import List, Optional
import networkx as nx

from shared.config import DEGRADATION_CEILING, DEGRADATION_STEP, POLL_INTERVAL_SEC, TOPIC_TELEMETRY
from shared.event_bus import bus
from shared.schemas import TelemetryReading
from network_sim.snmp_agent import agent_manager

logger = logging.getLogger("snmp_poller")


def poll_all_nodes(graph: Optional[nx.Graph] = None, timestamp: Optional[float] = None) -> List[TelemetryReading]:
    """
    Poll telemetry readings for all edges in the virtual network.
    Matches Master Section 6.3 interface and returns List[TelemetryReading].
    """
    if timestamp is None:
        timestamp = float(time.time())

    readings: List[TelemetryReading] = []

    if graph is None:
        return readings

    # Sync MIB tables first
    agent_manager.sync_telemetry(graph)

    import random

    for u, v, data in graph.edges(data=True):
        link_name = f"{u}-{v}"
        base_lat = float(data.get("base_latency", data.get("latency", 5.0)))
        jitter = float(data.get("jitter", 1.0))
        status = data.get("status", "healthy")
        oper_status = data.get("ifOperStatus", 1)

        # In SNMP polling, an interface that is down (ifOperStatus == 2 or status == "failed")
        # or attached to a crashed router (node status == "down") yields no SNMP response.
        # Exclude completely from telemetry readings for this calculation cycle.
        u_down = graph.nodes[u].get("status") == "down"
        v_down = graph.nodes[v].get("status") == "down"
        if oper_status == 2 or status == "failed" or u_down or v_down:
            continue

        # For healthy operational links, apply realistic dynamic micro-jitter around base_latency
        if status == "healthy" and oper_status == 1:
            delta = random.uniform(-0.15, 0.15) * jitter
            current_latency = round(max(2.0, base_lat + delta), 2)
            data["latency"] = current_latency
        elif status == "degrading" and oper_status == 1:
            # Progressive degradation: incrementally worsen telemetry metrics towards ceilings on each poll interval
            step = DEGRADATION_STEP
            ceil = DEGRADATION_CEILING

            new_lat = min(ceil.get("latency", 110.0), float(data.get("latency", base_lat)) + step.get("latency", 4.5))
            new_jit = min(ceil.get("jitter", 25.0), float(data.get("jitter", 1.0)) + step.get("jitter", 1.2))
            new_loss = min(ceil.get("packet_loss", 15.0), float(data.get("packet_loss", 0.0)) + step.get("packet_loss", 0.6))
            new_queue = min(ceil.get("queue", 80.0), float(data.get("queue", 0.0)) + step.get("queue", 3.5))
            new_util = min(ceil.get("utilization", 0.95), float(data.get("utilization", 0.2)) + step.get("utilization", 0.04))
            new_tp = max(ceil.get("throughput", 15.0), float(data.get("throughput", 100.0)) + step.get("throughput", -4.0))
            new_cong = min(ceil.get("congestion_level", 0.95), float(data.get("congestion_level", 0.0)) + step.get("congestion_level", 0.05))

            data["latency"] = round(new_lat, 2)
            data["jitter"] = round(new_jit, 2)
            data["packet_loss"] = round(new_loss, 2)
            data["queue"] = round(new_queue, 1)
            data["utilization"] = round(new_util, 3)
            data["throughput"] = round(new_tp, 2)
            data["congestion_level"] = round(new_cong, 3)

            current_latency = data["latency"]
            jitter = data["jitter"]
        else:
            current_latency = float(data.get("latency", base_lat))

        loss = float(data.get("packet_loss", 0.0))
        queue = float(data.get("queue", 0.0))
        throughput = float(data.get("throughput", 100.0))
        utilization = float(data.get("utilization", 0.2))

        reading = TelemetryReading(
            timestamp=round(timestamp, 3),
            link=link_name,
            latency=round(current_latency, 2),
            jitter=round(jitter, 2),
            packet_loss=round(loss, 2),
            queue=round(queue, 1),
            throughput=round(throughput, 2),
            utilization=round(utilization, 3),
            state=None,  # Ground truth state only present in training dataset
        )
        readings.append(reading)
        bus.publish(TOPIC_TELEMETRY, reading)

    # Sync MIB tables with updated edge telemetry
    agent_manager.sync_telemetry(graph)

    return readings


class SNMPPoller:
    """Poller runner that can execute periodic polls or single-step polls."""

    def __init__(self, graph: nx.Graph, interval_sec: float = POLL_INTERVAL_SEC):
        self.graph = graph
        self.interval_sec = interval_sec

    def poll_step(self, current_time: Optional[float] = None) -> List[TelemetryReading]:
        return poll_all_nodes(self.graph, timestamp=current_time)
