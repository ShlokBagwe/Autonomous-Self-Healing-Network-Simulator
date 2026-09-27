"""
Minimal, thread-safe in-process EventBus for publish/subscribe messaging across modules.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 5.
"""
import logging
import threading
from typing import Any, Callable, Dict, List

logger = logging.getLogger("event_bus")


class EventBus:
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """Register a callback for a specific topic."""
        with self._lock:
            self._subs.setdefault(topic, []).append(callback)

    def unsubscribe(self, topic: str, callback: Callable[[Any], None]) -> None:
        """Unregister a callback from a specific topic."""
        with self._lock:
            if topic in self._subs and callback in self._subs[topic]:
                self._subs[topic].remove(callback)

    def publish(self, topic: str, payload: Any) -> None:
        """Deliver payload to all subscribers registered for this topic."""
        with self._lock:
            subscribers = list(self._subs.get(topic, []))

        for cb in subscribers:
            try:
                cb(payload)
            except Exception as e:
                logger.error(f"Error in subscriber {cb} for topic '{topic}': {e}", exc_info=True)

    def clear(self) -> None:
        """Clear all subscriptions (useful in testing)."""
        with self._lock:
            self._subs.clear()


# Shared singleton instance as specified in master doc
bus = EventBus()
