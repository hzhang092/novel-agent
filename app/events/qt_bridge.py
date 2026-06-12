"""Qt thread bridge for the domain EventBus.

Marshals publish() calls from worker threads to the Qt main thread
via QTimer.singleShot(0, ...) which posts to the main event loop.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QThread, QTimer

from app.events.bus import EventBus


class QtEventBridge(QObject):
    """Wraps an EventBus so publish() is always safe from any thread."""

    def __init__(self, bus: EventBus, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.bus = bus

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event. Safe from any thread."""
        if QThread.currentThread() is self.thread():
            self.bus.publish(event_type, **payload)
        else:
            QTimer.singleShot(0, lambda: self.bus.publish(event_type, **payload))
