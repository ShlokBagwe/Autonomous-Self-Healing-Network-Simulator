"""
Routing Controller for Member 3.
Computes optimal surviving paths using NetworkX Dijkstra with the dynamic edge cost formula.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.5 and Plan_docs/member-3-self-healing.md.
"""
from dataclasses import asdict
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Tuple
import networkx as nx

from shared.config import (
    EVENTS_LOG_FILE,
    PENALTY_WEIGHT_CONGESTION,
    PENALTY_WEIGHT_FAILURE_RISK,
    PENALTY_WEIGHT_LATENCY,
    PENALTY_WEIGHT_LOSS,
    TOPIC_ALERT,
    TOPIC_FAULT,
    TOPIC_REROUTE,
)
from shared.event_bus import bus
from shared.schemas import Alert, RerouteEvent

logger = logging.getLogger("routing_controller")


def normalize_link_name(link: str) -> Tuple[str, str]:
    """Parse and normalize a link representation 'A-B' into ('A', 'B')."""
    parts = link.strip().split("-", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return link.strip(), ""


def calculate_edge_cost(
    u: str,
    v: str,
    edge_data: Dict,
    failed_element: Optional[str] = None,
    severity: float = 1.0,
    graph: Optional[nx.Graph] = None,
) -> float:
    """
    Compute edge cost according to Master Section 6.1:
    cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty
    Failed links and down nodes are penalized to effective infinity (1e9) so Dijkstra will never traverse them.
    """
    # 1. Physical interface down or status failed
    if edge_data.get("ifOperStatus") == 2 or edge_data.get("status") == "failed" or edge_data.get("packet_loss", 0.0) >= 100.0:
        return 1e9

    # 2. Incident router down
    if graph is not None:
        if graph.nodes[u].get("status") == "down" or graph.nodes[v].get("status") == "down":
            return 1e9

    # 3. Matches currently diagnosed hard failed element (severity >= 0.8)
    if failed_element and severity >= 0.8:
        u_f, v_f = normalize_link_name(failed_element)
        if v_f:
            if (u == u_f and v == v_f) or (u == v_f and v == u_f):
                return 1e9
        else:
            if u == failed_element or v == failed_element:
                return 1e9

    base_cost = float(edge_data.get("base_cost", edge_data.get("weight", 1.0)))
    latency = float(edge_data.get("latency", 0.0))
    loss = float(edge_data.get("packet_loss", 0.0))
    congestion = float(edge_data.get("congestion_level", edge_data.get("utilization", 0.0)))
    failure_risk = float(edge_data.get("failure_risk", 0.0))

    # Calculate penalties
    latency_penalty = latency * PENALTY_WEIGHT_LATENCY
    loss_penalty = loss * PENALTY_WEIGHT_LOSS
    congestion_penalty = congestion * PENALTY_WEIGHT_CONGESTION
    risk_penalty = failure_risk * PENALTY_WEIGHT_FAILURE_RISK

    total_cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + risk_penalty
    return float(total_cost)


def recalculate_route(
    graph: nx.Graph,
    source: str,
    dest: str,
    failed_element: Optional[str] = None,
    severity: float = 1.0,
) -> List[str]:
    """
    Recalculate route using NetworkX Dijkstra and dynamic edge costs.
    Excludes all failed edges and down nodes from the operational topology view.
    Congested links (severity < 0.8) remain part of the traversable graph at higher dynamic cost.
    """
    if source not in graph or dest not in graph:
        raise nx.NodeNotFound(f"Source '{source}' or Dest '{dest}' not found in graph.")

    # Only treat failed_element as an unusable hard failure if severity >= 0.8
    is_hard_failure = (failed_element is not None and severity >= 0.8)

    def is_operational_node(n):
        if is_hard_failure and failed_element == n:
            return False
        return graph.nodes[n].get("status") != "down"

    def is_operational_edge(u, v):
        if not (is_operational_node(u) and is_operational_node(v)):
            return False
        if is_hard_failure and failed_element:
            u_f, v_f = normalize_link_name(failed_element)
            if v_f and ((u == u_f and v == v_f) or (u == v_f and v == u_f)):
                return False
        ed = graph.edges[u, v]
        if ed.get("ifOperStatus") == 2 or ed.get("status") == "failed" or ed.get("packet_loss", 0.0) >= 100.0:
            return False
        return True

    op_graph = nx.subgraph_view(graph, filter_node=is_operational_node, filter_edge=is_operational_edge)

    def weight_func(u, v, data):
        return calculate_edge_cost(u, v, data, failed_element=failed_element, severity=severity, graph=graph)

    # Use NetworkX Dijkstra on strictly operational surviving topology
    path = nx.dijkstra_path(op_graph, source, dest, weight=weight_func)
    return path


class RoutingController:
    """
    Controller responsible for self-healing route recalculation and publishing RerouteEvents.
    Subscribes to 'alert.raised' and 'fault.injected' topics.
    """

    def __init__(self, graph: Optional[nx.Graph] = None):
        self.graph = graph if graph is not None else nx.Graph()
        self.active_paths: Dict[Tuple[str, str], List[str]] = {}
        self.fault_onset_times: Dict[str, float] = {}  # element -> t_fault_onset

        # Register event subscriptions
        bus.subscribe(TOPIC_ALERT, self.on_alert)
        bus.subscribe(TOPIC_FAULT, self.on_fault_injected)

    def set_graph(self, graph: nx.Graph) -> None:
        """Update current topology graph."""
        self.graph = graph

    def set_active_path(self, source: str, dest: str, path: List[str]) -> None:
        """Cache current primary path between source and dest."""
        self.active_paths[(source, dest)] = path

    def on_fault_injected(self, payload: Dict) -> None:
        """Record simulation fault onset timestamp for MTTR tracking."""
        target = payload.get("target")
        timestamp = payload.get("timestamp", time.time())
        if target:
            self.fault_onset_times[str(target)] = float(timestamp)

    def on_alert(self, alert: Alert) -> Optional[RerouteEvent]:
        """
        Handle incoming Alert, diagnose severity, recalculate route, and publish RerouteEvent.
        """
        from self_healing.diagnosis import diagnose

        if self.graph.number_of_nodes() == 0:
            logger.warning("RoutingController has no topology graph; skipping reroute.")
            return None

        # Run diagnosis
        diagnosis = diagnose(alert, self.graph)
        affected_element, severity = diagnosis.affected_element, diagnosis.severity

        # Identify which active paths are affected by this fault
        reroute_events = []
        u_f, v_f = normalize_link_name(affected_element)

        # Recalculate routes for monitored pairs or default topology pairs
        for (src, dst), current_path in list(self.active_paths.items()):
            is_affected = False

            if v_f:
                # Link fault: check if current_path uses (u_f, v_f) or (v_f, u_f)
                for i in range(len(current_path) - 1):
                    seg = (current_path[i], current_path[i + 1])
                    if seg == (u_f, v_f) or seg == (v_f, u_f):
                        is_affected = True
                        break
            else:
                # Node fault: check if current_path passes through affected_element
                if affected_element in current_path:
                    is_affected = True

            # Also verify if current_path contains ANY link or node that is down in graph
            if not is_affected:
                for i in range(len(current_path) - 1):
                    u_c, v_c = current_path[i], current_path[i + 1]
                    if self.graph.has_edge(u_c, v_c):
                        ed = self.graph.edges[u_c, v_c]
                        if ed.get("ifOperStatus") == 2 or ed.get("status") == "failed" or ed.get("packet_loss", 0.0) >= 100.0:
                            is_affected = True
                            break
                    if self.graph.nodes[u_c].get("status") == "down" or self.graph.nodes[v_c].get("status") == "down":
                        is_affected = True
                        break

            if is_affected:
                event = self.heal_path(src, dst, alert, severity=severity)
                if event:
                    reroute_events.append(event)

        return reroute_events[0] if reroute_events else None

    def heal_path(
        self,
        source: str,
        dest: str,
        trigger_alert: Alert,
        severity: float = 1.0,
        current_time: Optional[float] = None,
    ) -> Optional[RerouteEvent]:
        """
        Heal a specific source-destination path affected by an alert.
        Recalculates route, updates cache, logs to events.jsonl, and publishes RerouteEvent.
        """
        if current_time is None:
            current_time = float(time.time())

        failed_link = trigger_alert.link
        old_path = self.active_paths.get((source, dest), [])

        try:
            new_path = recalculate_route(
                self.graph,
                source=source,
                dest=dest,
                failed_element=failed_link,
                severity=severity,
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound) as e:
            logger.warning(f"No surviving route from {source} to {dest}: {e}")
            new_path = []

        # Compute recovery latency in milliseconds relative to t_fault_onset (or alert timestamp)
        onset_time = self.fault_onset_times.pop(failed_link, trigger_alert.timestamp)
        if onset_time < trigger_alert.timestamp - 5.0:
            onset_time = trigger_alert.timestamp
        recovery_latency_ms = max(0.0, (current_time - onset_time) * 1000.0)

        reroute_event = RerouteEvent(
            timestamp=current_time,
            failed_link=failed_link,
            old_path=old_path,
            new_path=new_path,
            trigger_alert=trigger_alert,
            recovery_latency_ms=round(recovery_latency_ms, 2),
        )

        # Update cached active path
        self.active_paths[(source, dest)] = new_path

        # Publish to event bus topic
        bus.publish(TOPIC_REROUTE, reroute_event)

        # Append to unified events.jsonl
        self._log_event(reroute_event)

        return reroute_event

    def _log_event(self, event: RerouteEvent) -> None:
        """Append RerouteEvent to logs/events.jsonl in JSON format."""
        try:
            EVENTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log_entry = {
                "type": "reroute.completed",
                "payload": asdict(event),
            }
            with open(EVENTS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to append reroute event to {EVENTS_LOG_FILE}: {e}")
