"""
Live ML Inference Service for Member 2.
Subscribes to 'telemetry.reading', performs live classification via trained Random Forest model,
and publishes Alert(source='ml_engine', ...) to 'alert.raised' on abnormal states.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.4 and Plan_docs/member-2-ml-engine.md.
"""
import logging
from typing import Dict, Optional

from shared.config import TOPIC_ALERT, TOPIC_TELEMETRY
from shared.event_bus import bus
from shared.schemas import Alert, TelemetryReading
from ml_engine.random_forest import NetworkStateClassifier

logger = logging.getLogger("ml_inference")


def _canonical_link(link: str) -> str:
    """Normalize 'A-B' and 'B-A' to the same key."""
    if "-" in link:
        parts = link.split("-", 1)
        return "-".join(sorted(p.strip() for p in parts))
    return link.strip()


class MLInferenceService:
    def __init__(self, classifier: Optional[NetworkStateClassifier] = None, auto_subscribe: bool = True):
        self.classifier = classifier or NetworkStateClassifier()
        self.total_inferences = 0
        self.alerts_published = 0
        # In-memory map: link -> last known predicted state
        self.last_predicted_state: Dict[str, str] = {}

        if auto_subscribe:
            bus.subscribe(TOPIC_TELEMETRY, self.on_telemetry_reading)

    def reset_state(self) -> None:
        """Clear state-tracking cache (called on network reset)."""
        self.last_predicted_state.clear()
        logger.info("MLInferenceService state tracking cleared.")

    def on_telemetry_reading(self, reading: TelemetryReading) -> Optional[Alert]:
        """
        Evaluate reading with ML model. Only publish an Alert when the predicted
        state for a link changes (e.g. healthy -> congested, congested -> healthy).
        Do not alert again on every poll while the state is unchanged.
        """
        self.total_inferences += 1
        features = {
            "latency": reading.latency,
            "jitter": reading.jitter,
            "packet_loss": reading.packet_loss,
            "queue": reading.queue,
            "throughput": reading.throughput,
            "utilization": reading.utilization,
        }

        try:
            predicted_state, confidence = self.classifier.predict(features)
        except Exception as e:
            logger.error(f"Inference error on reading {reading.link}: {e}")
            return None

        canon_link = _canonical_link(reading.link)
        prev_state = self.last_predicted_state.get(canon_link, "healthy")
        self.last_predicted_state[canon_link] = predicted_state

        # Only alert on state change from previous state (Option B: alert on transition)
        if predicted_state != "healthy" and predicted_state != prev_state:
            alert = Alert(
                timestamp=reading.timestamp,
                source="ml_engine",
                link=reading.link,
                predicted_state=predicted_state,
                confidence=confidence,
            )
            self.alerts_published += 1
            bus.publish(TOPIC_ALERT, alert)
            logger.info(
                f"ML state transition alert on {reading.link}: {prev_state} -> {predicted_state} "
                f"(confidence: {confidence:.2f})"
            )
            return alert

        return None
