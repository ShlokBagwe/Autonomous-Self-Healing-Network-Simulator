"""
SNMP TRAP Listener for Member 1.
Receives incoming SNMP TRAPs from simulated agents and publishes Alert objects to 'alert.raised'.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.3.
"""
import logging
from typing import Callable, List, Optional

from shared.config import TOPIC_ALERT
from shared.event_bus import bus
from shared.schemas import Alert

logger = logging.getLogger("trap_listener")


class TrapListener:
    """Listens for SNMP TRAPs and routes them to the event bus."""

    def __init__(self, on_trap_callback: Optional[Callable[[Alert], None]] = None):
        self.received_traps: List[Alert] = []
        self.callback = on_trap_callback

    def handle_trap(self, target: str, timestamp: float) -> Alert:
        """Construct Alert(source='snmp_trap', ...) and publish to 'alert.raised'."""
        alert = Alert(
            timestamp=timestamp,
            source="snmp_trap",
            link=target,
            predicted_state="failed",
            confidence=None,
        )
        self.received_traps.append(alert)
        bus.publish(TOPIC_ALERT, alert)
        if self.callback:
            self.callback(alert)
        return alert
