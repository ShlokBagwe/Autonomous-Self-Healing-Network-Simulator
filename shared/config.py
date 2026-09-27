"""
Shared configuration constants across all modules.
Defined in Plan_docs/00_PROJECT_MASTER.md and member specifications.
"""
from pathlib import Path

# Base Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = PROJECT_ROOT / "logs"
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = DATA_DIR / "models"
RAW_DATA_DIR = DATA_DIR / "raw"
EVENTS_LOG_FILE = LOGS_DIR / "events.jsonl"

# Simulation Constants
POLL_INTERVAL_SEC = 1.0
DEFAULT_NODE_COUNT = 10

# Member 3: Reconciliation Window
RECONCILE_WINDOW_SEC = 2.0

# Dynamic Edge Cost Formula Weights (Member 1 & Member 3)
# cost = base_cost + latency_penalty + loss_penalty + congestion_penalty + failure_risk_penalty
PENALTY_WEIGHT_LATENCY = 0.5        # latency in ms * weight
PENALTY_WEIGHT_LOSS = 10.0          # packet loss percentage * weight
PENALTY_WEIGHT_CONGESTION = 20.0    # congestion score (0.0 to 1.0) * weight
PENALTY_WEIGHT_FAILURE_RISK = 1000.0  # failure risk (0.0 to 1.0) or 1e6 when link down

# SNMP Base OID Mapping (Member 1)
OID_BASE = "1.3.6.1.4.1.9999.1"
OID_MAP = {
    f"{OID_BASE}.1": "latency",
    f"{OID_BASE}.2": "jitter",
    f"{OID_BASE}.3": "packet_loss",
    f"{OID_BASE}.4": "queue_size",
    f"{OID_BASE}.5": "throughput",
    f"{OID_BASE}.6": "bandwidth_utilization",
    f"{OID_BASE}.7": "ifOperStatus",
    f"{OID_BASE}.8": "ifInErrors",
}

# Event Bus Topics
TOPIC_TELEMETRY = "telemetry.reading"
TOPIC_ALERT = "alert.raised"
TOPIC_REROUTE = "reroute.completed"
TOPIC_FAULT = "fault.injected"
