"""
Alert Reconciler for Member 3.
Compares reactive SNMP TRAPs vs proactive ML Engine alerts to evaluate agreement and latency deltas.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.5 and Plan_docs/member-3-self-healing.md.
"""
from dataclasses import asdict
import json
import logging
import threading
import time
from typing import Dict, List, Optional

from shared.config import (
    EVENTS_LOG_FILE,
    RECONCILE_WINDOW_SEC,
    TOPIC_ALERT,
)
from shared.event_bus import bus
from shared.schemas import Alert, ReconciliationRecord

logger = logging.getLogger("alert_reconciler")


def normalize_link_key(link: str) -> str:
    """
    Normalize link representation to canonical undirected form (e.g. 'F-E' -> 'E-F', or 'A' -> 'A').
    Ensures identical link matching regardless of endpoint ordering.
    """
    parts = link.strip().split("-", 1)
    if len(parts) == 2:
        u, v = parts[0].strip(), parts[1].strip()
        return f"{min(u, v)}-{max(u, v)}"
    return link.strip()


class AlertReconciler:
    """
    Subscribes to 'alert.raised', pairs SNMP TRAP and ML alerts within RECONCILE_WINDOW_SEC,
    records agreement vs single-source alerts, and logs reconciliation data to logs/events.jsonl.
    """

    def __init__(self, window_sec: float = RECONCILE_WINDOW_SEC, auto_subscribe: bool = True):
        self.window_sec = float(window_sec)
        self.unpaired_alerts: Dict[str, List[Alert]] = {}
        self.reconciliation_history: List[ReconciliationRecord] = []
        self._lock = threading.RLock()

        if auto_subscribe:
            bus.subscribe(TOPIC_ALERT, self.on_alert)

    def on_alert(self, alert: Alert) -> Optional[ReconciliationRecord]:
        """Callback for 'alert.raised' event bus topic."""
        with self._lock:
            # 1. Log incoming alert to events.jsonl
            self._log_raw_alert(alert)

            # 2. Check for expired pending alerts before processing
            self.flush_pending(current_time=alert.timestamp)

            # 3. Attempt reconciliation
            return self.process_alert(alert)

    def process_alert(self, alert: Alert) -> Optional[ReconciliationRecord]:
        """
        Process an incoming alert against pending alerts for the same link.
        Returns a ReconciliationRecord if agreement occurs, else buffers the alert.
        """
        with self._lock:
            canonical_link = normalize_link_key(alert.link)
            pending_list = self.unpaired_alerts.setdefault(canonical_link, [])

            # Search for a matching alert: MUST be opposite source AND identical link AND within time window
            matched_index = None
            for idx, pending in enumerate(pending_list):
                is_opposite_source = (pending.source != alert.source)
                is_same_link = (normalize_link_key(pending.link) == canonical_link)
                time_delta = abs(alert.timestamp - pending.timestamp)
                is_within_window = (time_delta <= self.window_sec)

                if is_opposite_source and is_same_link and is_within_window:
                    matched_index = idx
                    break

            if matched_index is not None:
                # Opposite alert found within window -> Agreement!
                pending = pending_list.pop(matched_index)

                trap_alert = alert if alert.source == "snmp_trap" else pending
                ml_alert = alert if alert.source == "ml_engine" else pending

                time_delta_sec = round(abs(trap_alert.timestamp - ml_alert.timestamp), 4)

                record = ReconciliationRecord(
                    timestamp=alert.timestamp,
                    link=canonical_link,
                    agreement=True,
                    sources=["snmp_trap", "ml_engine"],
                    trap_timestamp=trap_alert.timestamp,
                    ml_timestamp=ml_alert.timestamp,
                    time_delta_sec=time_delta_sec,
                    ml_confidence=ml_alert.confidence,
                    predicted_state=ml_alert.predicted_state,
                )

                self.reconciliation_history.append(record)
                self._log_reconciliation(record)
                return record
            else:
                # No match yet; buffer this alert awaiting possible companion
                pending_list.append(alert)
                return None

    def flush_pending(self, current_time: Optional[float] = None) -> List[ReconciliationRecord]:
        """
        Flush pending alerts that have exceeded the reconciliation time window without a companion.
        Records agreement=False with single source.
        """
        if current_time is None:
            current_time = float(time.time())

        flushed_records: List[ReconciliationRecord] = []

        with self._lock:
            for link, alerts in list(self.unpaired_alerts.items()):
                remaining = []
                for alert in alerts:
                    if (current_time - alert.timestamp) > self.window_sec:
                        # Window expired with only one source firing
                        trap_ts = alert.timestamp if alert.source == "snmp_trap" else None
                        ml_ts = alert.timestamp if alert.source == "ml_engine" else None

                        record = ReconciliationRecord(
                            timestamp=alert.timestamp,
                            link=link,
                            agreement=False,
                            sources=[alert.source],
                            trap_timestamp=trap_ts,
                            ml_timestamp=ml_ts,
                            time_delta_sec=None,
                            ml_confidence=alert.confidence if alert.source == "ml_engine" else None,
                            predicted_state=alert.predicted_state,
                        )
                        self.reconciliation_history.append(record)
                        self._log_reconciliation(record)
                        flushed_records.append(record)
                    else:
                        remaining.append(alert)

                if remaining:
                    self.unpaired_alerts[link] = remaining
                else:
                    self.unpaired_alerts.pop(link, None)

        return flushed_records

    def get_summary_stats(self) -> Dict:
        """
        Compute high-level reconciliation metrics for Member 4 evaluation.
        """
        with self._lock:
            total = len(self.reconciliation_history)
            if total == 0:
                return {
                    "total_records": 0,
                    "agreements": 0,
                    "agreement_rate": 0.0,
                    "trap_only": 0,
                    "ml_only": 0,
                    "mean_time_delta_sec": 0.0,
                }

            agreements = sum(1 for r in self.reconciliation_history if r.agreement)
            trap_only = sum(1 for r in self.reconciliation_history if not r.agreement and "snmp_trap" in r.sources)
            ml_only = sum(1 for r in self.reconciliation_history if not r.agreement and "ml_engine" in r.sources)

            deltas = [r.time_delta_sec for r in self.reconciliation_history if r.time_delta_sec is not None]
            mean_delta = sum(deltas) / len(deltas) if deltas else 0.0

            return {
                "total_records": total,
                "agreements": agreements,
                "agreement_rate": round(agreements / total, 4),
                "trap_only": trap_only,
                "ml_only": ml_only,
                "mean_time_delta_sec": round(mean_delta, 4),
            }

    def _log_raw_alert(self, alert: Alert) -> None:
        """Append raw alert to logs/events.jsonl."""
        try:
            EVENTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log_entry = {
                "type": "alert.raised",
                "payload": asdict(alert),
            }
            with open(EVENTS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log alert to {EVENTS_LOG_FILE}: {e}")

    def _log_reconciliation(self, record: ReconciliationRecord) -> None:
        """Append reconciliation record to logs/events.jsonl."""
        try:
            EVENTS_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            log_entry = {
                "type": "reconciliation",
                "payload": asdict(record),
            }
            with open(EVENTS_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log reconciliation record to {EVENTS_LOG_FILE}: {e}")
