"""Async publish/subscribe event bus."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ugaf.core.exceptions import EventBusError
from ugaf.core.logger import Logger, get_logger

__all__ = [
    "Event",
    "EventBus",
    "EventBusError",
    "EventHandler",
]


@dataclass(frozen=True)
class Event:
    """Immutable event payload.

    Attributes:
        topic: Event topic (e.g. ``"bot.started"``, ``"vision.screenshot"``).
        data: Arbitrary event payload.

    """

    topic: str
    data: dict[str, Any] = field(default_factory=dict)


EventHandler = Callable[[Event], Awaitable[None]]
"""Type alias for an async event handler."""


class EventBus:
    """Async pub/sub event bus.

    Handlers are async callables that receive an ``Event``. The bus
    supports wildcard subscriptions with ``*`` matching a single level
    and ``**`` matching any remaining levels.

    Usage::

        bus = EventBus()

        async def on_start(event: Event) -> None:
            print(f"Started: {event.data}")

        await bus.subscribe("bot.*", on_start)
        await bus.publish(Event("bot.started", {"pid": 42}))
        await bus.unsubscribe("bot.*", on_start)
    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialise the event bus.

        Args:
            logger: Optional logger instance. Falls back to the global
                logger if not provided.

        """
        self._logger = logger or get_logger()
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, handler: EventHandler) -> None:
        """Subscribe a handler to a topic pattern.

        Args:
            topic: Topic pattern. May contain ``*`` (single-level) or
                ``**`` (multi-level) wildcards.
            handler: Async callable that receives the event.

        Raises:
            EventBusError: If the handler is not an async callable.

        """
        if not inspect.iscoroutinefunction(handler):
            raise EventBusError(f"Handler {handler!r} must be an async callable")

        async with self._lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = []
            self._subscribers[topic].append(handler)
            self._logger.debug(
                "event_bus.subscribed",
                topic=topic,
                handler=handler.__name__,
            )

    async def unsubscribe(self, topic: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from a topic pattern.

        Args:
            topic: The exact topic pattern used during subscription.
            handler: The handler to remove.

        Raises:
            EventBusError: If the handler is not found.

        """
        async with self._lock:
            handlers = self._subscribers.get(topic)
            if handlers is None or handler not in handlers:
                raise EventBusError(f"Handler {handler!r} not subscribed to topic {topic!r}")
            handlers.remove(handler)
            if not handlers:
                del self._subscribers[topic]
            self._logger.debug(
                "event_bus.unsubscribed",
                topic=topic,
                handler=handler.__name__,
            )

    async def publish(self, event: Event) -> None:
        """Publish an event to all matching subscribers.

        Args:
            event: The event to publish.

        Raises:
            EventBusError: If a handler raises an exception.

        """
        self._logger.debug("event_bus.publish", topic=event.topic)
        matched = self._match_subscribers(event.topic)

        for handler in matched:
            try:
                await handler(event)
            except Exception as exc:
                self._logger.error(
                    "event_bus.handler_failed",
                    topic=event.topic,
                    handler=handler.__name__,
                    error=str(exc),
                )
                raise EventBusError(
                    f"Handler {handler.__name__!r} failed for topic " f"{event.topic!r}: {exc}"
                ) from exc

    def _match_subscribers(self, topic: str) -> list[EventHandler]:
        """Collect handlers whose pattern matches the given topic.

        Supports ``*`` (single-level) and ``**`` (multi-level) wildcards.

        Args:
            topic: The published event topic.

        Returns:
            List of matching handlers from all matching patterns.

        """
        topic_parts = topic.split(".")
        matched: list[EventHandler] = []

        for pattern, handlers in self._subscribers.items():
            pattern_parts = pattern.split(".")
            if _pattern_matches(topic_parts, pattern_parts):
                matched.extend(handlers)

        return matched

    async def clear(self) -> None:
        """Remove all subscribers."""
        async with self._lock:
            self._subscribers.clear()
        self._logger.debug("event_bus.cleared")

    @property
    def subscriber_count(self) -> int:
        """Return the total number of registered handlers."""
        return sum(len(h) for h in self._subscribers.values())


def _pattern_matches(topic_parts: list[str], pattern_parts: list[str]) -> bool:
    """Check whether a topic matches a wildcard pattern.

    Args:
        topic_parts: Split topic segments.
        pattern_parts: Split pattern segments.

    Returns:
        ``True`` if the topic matches the pattern.

    """
    ti = 0
    pi = 0

    while ti < len(topic_parts) and pi < len(pattern_parts):
        if pattern_parts[pi] == "**":
            remaining_pattern = pattern_parts[pi + 1 :]
            for i in range(ti, len(topic_parts) + 1):
                if _pattern_matches(topic_parts[i:], remaining_pattern):
                    return True
            return False
        if pattern_parts[pi] != "*" and pattern_parts[pi] != topic_parts[ti]:
            return False
        ti += 1
        pi += 1

    # Remaining pattern segments can only be "**"
    while pi < len(pattern_parts):
        if pattern_parts[pi] != "**":
            return False
        pi += 1

    return ti == len(topic_parts) and pi == len(pattern_parts)
