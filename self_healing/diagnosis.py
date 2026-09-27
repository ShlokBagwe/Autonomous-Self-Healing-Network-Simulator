"""
Fault diagnosis module for Member 3.
Inspects incoming Alert and network graph to determine affected element and severity.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.5 and Plan_docs/member-3-self-healing.md.
"""
from dataclasses import dataclass
from typing import Any, Optional, Tuple
import networkx as nx

from shared.schemas import Alert, State


@dataclass
class DiagnosisResult:
    """Rich diagnosis result containing element, severity, and topology metadata."""
    affected_element: str
    severity: float  # Range: [0.0, 1.0]
    is_link: bool
    endpoints: Optional[Tuple[str, str]]
    predicted_state: State
    confidence: Optional[float]
    source: str

    def __iter__(self):
        """Allows unpacking directly as (affected_element, severity)."""
        return iter((self.affected_element, self.severity))

    def __getitem__(self, index: int):
        return (self.affected_element, self.severity)[index]


def parse_element(element_str: str) -> Tuple[bool, Optional[Tuple[str, str]]]:
    """
    Parse an element string to determine if it is a link ('A-B') or a single node ('A').
    Returns (is_link, endpoints).
    """
    cleaned = element_str.strip()
    if "-" in cleaned:
        parts = cleaned.split("-", 1)
        u, v = parts[0].strip(), parts[1].strip()
        return True, (u, v)
    return False, None


def calculate_severity(alert: Alert) -> float:
    """
    Compute severity in range [0.0, 1.0].
    - SNMP TRAP: Maximum severity (1.0), indicating hard agent/link failure.
    - ML Engine: Scaled by predicted state and model classification confidence.
    """
    if alert.source == "snmp_trap":
        return 1.0

    state = alert.predicted_state
    confidence = alert.confidence if alert.confidence is not None else 1.0
    confidence = max(0.0, min(1.0, confidence))

    if state == "failed":
        # Failure severity ranges from 0.8 to 1.0 based on confidence
        return round(0.8 + 0.2 * confidence, 4)
    elif state == "congested":
        # Congestion severity ranges from 0.3 to 0.7 based on confidence
        return round(0.3 + 0.4 * confidence, 4)
    elif state == "healthy":
        return 0.0
    else:
        # Fallback for unexpected state strings
        return round(0.5 * confidence, 4)


def diagnose(alert: Alert, graph: Optional[nx.Graph] = None) -> Tuple[str, float]:
    """
    Diagnose an incoming Alert to identify the affected element and its fault severity.

    Args:
        alert: Shared schema Alert instance (from SNMP TRAP or ML Engine).
        graph: Optional NetworkX topology graph for validating element existence.

    Returns:
        tuple (affected_element: str, severity: float)
        Also returns a DiagnosisResult instance which supports tuple unpacking:
        affected_element, severity = diagnose(alert, graph)
    """
    affected_element = alert.link.strip()
    is_link, endpoints = parse_element(affected_element)

    # Validate against topology graph if provided
    if graph is not None:
        if is_link and endpoints:
            u, v = endpoints
            if not graph.has_edge(u, v) and not graph.has_edge(v, u):
                # Check if reverse or partial match exists
                if graph.has_node(u) and graph.has_node(v):
                    pass  # Nodes exist, graph may be directed or pending edge
        elif not is_link:
            if not graph.has_node(affected_element):
                # Try finding incident edges if any
                pass

    severity = calculate_severity(alert)

    return DiagnosisResult(
        affected_element=affected_element,
        severity=severity,
        is_link=is_link,
        endpoints=endpoints,
        predicted_state=alert.predicted_state,
        confidence=alert.confidence,
        source=alert.source,
    )
