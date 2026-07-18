"""Qt thread bridge for the domain EventBus.

Marshals publish() calls from worker threads to the Qt main thread.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from app.events.bus import EventBus


class QtEventBridge(QObject):
    """Wraps an EventBus so publish() is always safe from any thread.

    Usage::

        domain_bus = EventBus()
        bridge = QtEventBridge(domain_bus)
        bridge.publish("character_state_updated", character_id="x", event_id=1)
    """

    _publish_requested = Signal(str, object)

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus
        self._publish_requested.connect(
            self._on_publish,
            Qt.ConnectionType.QueuedConnection,
        )

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event. Safe from any thread."""
        if QThread.currentThread() is self.thread():
            self.bus.publish(event_type, **payload)
        else:
            self._publish_requested.emit(event_type, payload)

    @Slot(str, object)
    def _on_publish(self, event_type: str, payload: dict[str, object]) -> None:
        """Receiver slot — always runs on the bridge's owning thread."""
        self.bus.publish(event_type, **payload)
