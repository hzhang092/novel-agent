"""Tests for QtEventBridge cross-thread dispatch."""
import pytest
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication

from app.events.bus import EventBus
from app.events.qt_bridge import QtEventBridge


class TestQtEventBridge:
    def test_publish_from_main_thread_calls_handler_directly(self, qtbot):
        """When called from the main thread, handler runs synchronously."""
        bus = EventBus()
        bridge = QtEventBridge(bus)
        received = []

        bus.subscribe("test_event", lambda **kw: received.append(kw))
        bridge.publish("test_event", key="direct")

        assert len(received) == 1
        assert received[0]["key"] == "direct"

    def test_publish_from_worker_thread_dispatches_to_main(self, qtbot):
        """When called from a QThread, the handler runs on the main thread
        via QTimer.singleShot queued dispatch."""
        bus = EventBus()
        bridge = QtEventBridge(bus)
        received = []

        def handler(**kw):
            # Verify we're on the main thread when the handler fires
            assert QThread.currentThread() is QApplication.instance().thread(), (
                "handler must run on the main thread"
            )
            received.append(kw)

        bus.subscribe("test_event", handler)

        class Worker(QThread):
            def run(self):
                bridge.publish("test_event", key="from_worker")

        worker = Worker()
        worker.start()
        worker.wait()  # block until worker finishes

        # The queued publish hasn't landed yet — process events
        def check():
            assert len(received) == 1
            assert received[0]["key"] == "from_worker"

        QTimer.singleShot(50, check)
        # Let the event loop spin to deliver the queued call + check timer
        qtbot.waitUntil(lambda: len(received) == 1, timeout=2000)

    def test_publish_from_worker_with_no_subscribers_does_not_crash(self, qtbot):
        """Publishing from a worker thread with no subscribers is safe."""
        bus = EventBus()
        bridge = QtEventBridge(bus)

        class Worker(QThread):
            def run(self):
                bridge.publish("no_listeners", key="nobody")

        worker = Worker()
        worker.start()
        worker.wait()
        # No crash = pass
