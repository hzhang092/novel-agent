
"""Tests for the domain event bus — pure Python, no Qt."""
import pytest
from app.events.bus import EventBus


class TestEventBus:
    def test_subscribe_and_publish_single_handler(self):
        bus = EventBus()
        received = []

        bus.subscribe("character_state_updated", lambda **kw: received.append(kw))
        bus.publish("character_state_updated", character_id="char-1", event_id=42)

        assert len(received) == 1
        assert received[0]["character_id"] == "char-1"
        assert received[0]["event_id"] == 42

    def test_publish_with_no_subscribers_does_not_raise(self):
        bus = EventBus()
        bus.publish("unknown_event", foo="bar")

    def test_multiple_handlers_for_same_event(self):
        bus = EventBus()
        calls = []

        bus.subscribe("evt", lambda **kw: calls.append(1))
        bus.subscribe("evt", lambda **kw: calls.append(2))
        bus.publish("evt")

        assert calls == [1, 2]

    def test_handler_exception_does_not_block_others(self):
        bus = EventBus()
        calls = []

        def bad_handler(**kw):
            raise RuntimeError("boom")

        bus.subscribe("evt", bad_handler)
        bus.subscribe("evt", lambda **kw: calls.append("ok"))
        bus.publish("evt")

        assert calls == ["ok"]

    def test_unsubscribe_removes_handler(self):
        bus = EventBus()
        calls = []

        def h(**kw):
            calls.append(1)

        bus.subscribe("evt", h)
        bus.unsubscribe("evt", h)
        bus.publish("evt")

        assert calls == []
