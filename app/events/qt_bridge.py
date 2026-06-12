"""Qt thread bridge for the domain EventBus.

Marshals publish() calls from worker threads to the Qt main thread
via a pyqtSignal, which Qt automatically queues when the emitter
and receiver live on different threads.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from app.events.bus import EventBus


class QtEventBridge(QObject):
    """Wraps an EventBus so publish() is always safe from any thread.

    Usage::

        domain_bus = EventBus()
        bridge = QtEventBridge(domain_bus)
        bridge.publish("character_state_updated", character_id="x", event_id=1)
    """

    # Qt auto-queues this signal when emitter and receiver are on different threads
    _publish_requested = pyqtSignal(str, object)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus
        self._publish_requested.connect(self._on_publish)

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event. Safe from any thread."""
        if QThread.currentThread() is self.thread():
            self.bus.publish(event_type, **payload)
        else:
            # Emitting a signal across threads → Qt queues it on the receiver's thread
            self._publish_requested.emit(event_type, payload)

    def _on_publish(self, event_type: str, payload: dict) -> None:
        """Receiver slot — always runs on the bridge's owning thread."""
        self.bus.publish(event_type, **payload)
