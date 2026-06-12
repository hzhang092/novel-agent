"""Pure-Python event bus. No Qt, no threading logic."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable


Handler = Callable[..., None]


class EventBus:
    """Simple typed pub/sub bus for domain events.

    Usage::
        bus = EventBus()
        bus.subscribe("character_state_updated", lambda **kw: print(kw))
        bus.publish("character_state_updated", character_id="x", event_id=1)
    """

    def __init__(self) -> None:
        self._listeners: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        """Register a handler for an event type."""
        self._listeners[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: Handler) -> None:
        """Remove a handler for an event type. No-op if not registered."""
        try:
            self._listeners[event_type].remove(handler)
        except ValueError:
            pass

    def publish(self, event_type: str, **payload: object) -> None:
        """Publish an event to all registered handlers.
        Handlers are called synchronously. Exceptions in one handler
        do not prevent other handlers from running."""
        for handler in self._listeners.get(event_type, ()):
            try:
                handler(**payload)
            except Exception:
                # Swallow — one broken handler shouldn't break the bus.
                pass
