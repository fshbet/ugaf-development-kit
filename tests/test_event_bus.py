"""Tests for the Event Bus module."""

from __future__ import annotations

import pytest

from ugaf.core.event_bus import Event, EventBus, EventBusError


@pytest.mark.asyncio
async def test_subscribe_and_publish() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("test.topic", handler)
    event = Event(topic="test.topic", data={"key": "value"})
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].topic == "test.topic"
    assert received[0].data["key"] == "value"


@pytest.mark.asyncio
async def test_unsubscribe_removes_handler() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("test.topic", handler)
    await bus.unsubscribe("test.topic", handler)
    await bus.publish(Event(topic="test.topic"))

    assert len(received) == 0


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent_raises() -> None:
    bus = EventBus()

    async def handler(event: Event) -> None:
        pass

    with pytest.raises(EventBusError, match="not subscribed"):
        await bus.unsubscribe("test.topic", handler)


@pytest.mark.asyncio
async def test_subscribe_to_wildcard() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("bot.*", handler)
    await bus.publish(Event(topic="bot.started"))
    await bus.publish(Event(topic="bot.stopped"))
    await bus.publish(Event(topic="other.event"))

    assert len(received) == 2
    assert received[0].topic == "bot.started"
    assert received[1].topic == "bot.stopped"


@pytest.mark.asyncio
async def test_subscribe_to_multi_level_wildcard() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("plugin.**", handler)
    await bus.publish(Event(topic="plugin.loaded"))
    await bus.publish(Event(topic="plugin.game.started"))
    await bus.publish(Event(topic="other.event"))

    assert len(received) == 2


@pytest.mark.asyncio
async def test_subscribe_with_non_async_handler_raises() -> None:
    bus = EventBus()

    def sync_handler(event: Event) -> None:
        pass

    with pytest.raises(EventBusError, match="async"):
        await bus.subscribe("test", sync_handler)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_handler_exception_propagates() -> None:
    bus = EventBus()

    async def failing_handler(event: Event) -> None:
        raise ValueError("oops")

    await bus.subscribe("test", failing_handler)

    with pytest.raises(EventBusError, match="oops"):
        await bus.publish(Event(topic="test"))


@pytest.mark.asyncio
async def test_multiple_handlers_on_same_topic() -> None:
    bus = EventBus()
    results: list[int] = []

    async def handler_a(event: Event) -> None:
        results.append(1)

    async def handler_b(event: Event) -> None:
        results.append(2)

    await bus.subscribe("topic", handler_a)
    await bus.subscribe("topic", handler_b)
    await bus.publish(Event(topic="topic"))

    assert sorted(results) == [1, 2]


@pytest.mark.asyncio
async def test_clear_removes_all() -> None:
    bus = EventBus()

    async def handler(event: Event) -> None:
        pass

    await bus.subscribe("a", handler)
    await bus.subscribe("b", handler)
    assert bus.subscriber_count == 2

    await bus.clear()
    assert bus.subscriber_count == 0


@pytest.mark.asyncio
async def test_subscriber_count() -> None:
    bus = EventBus()

    async def handler(event: Event) -> None:
        pass

    assert bus.subscriber_count == 0
    await bus.subscribe("a", handler)
    assert bus.subscriber_count == 1
    await bus.subscribe("a", handler)
    assert bus.subscriber_count == 2


@pytest.mark.asyncio
async def test_publish_no_subscribers() -> None:
    bus = EventBus()
    await bus.publish(Event(topic="orphan"))


@pytest.mark.asyncio
async def test_mid_wildcard_does_not_greedy_match() -> None:
    bus = EventBus()
    received: list[Event] = []

    async def handler(event: Event) -> None:
        received.append(event)

    await bus.subscribe("**.start", handler)
    await bus.publish(Event(topic="app.start"))
    await bus.publish(Event(topic="app.stop"))

    assert len(received) == 1
    assert received[0].topic == "app.start"
