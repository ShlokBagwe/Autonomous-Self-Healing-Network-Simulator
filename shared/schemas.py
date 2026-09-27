"""
Shared schemas across all modules in Autonomous Self-Healing Network Simulator.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 5.
"""

from dataclasses import dataclass, asdict
from typing import Literal, Optional

State = Literal["healthy", "congested", "failed"]

@dataclass
class TelemetryReading:
    timestamp: float
    link: str            # e.g. "A-B"
    latency: float
    jitter: float
    packet_loss: float
    queue: float
    throughput: float
    utilization: float
    state: Optional[State] = None   # ground truth, only present in training data

@dataclass
class Alert:
    timestamp: float
    source: Literal["snmp_trap", "ml_engine"]
    link: str
    predicted_state: State
    confidence: Optional[float] = None   # ML only; None for TRAP

@dataclass
class RerouteEvent:
    timestamp: float
    failed_link: str
    old_path: list[str]
    new_path: list[str]
    trigger_alert: Alert
    recovery_latency_ms: Optional[float] = None

@dataclass
class ReconciliationRecord:
    timestamp: float
    link: str
    agreement: bool
    sources: list[str]
    trap_timestamp: Optional[float] = None
    ml_timestamp: Optional[float] = None
    time_delta_sec: Optional[float] = None
    ml_confidence: Optional[float] = None
    predicted_state: Optional[State] = None
