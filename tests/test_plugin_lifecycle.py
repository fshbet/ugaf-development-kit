"""Tests for PluginLifecycle."""

from __future__ import annotations

from typing import Any

import pytest

from ugaf.core.event_bus import Event, EventBus
from ugaf.plugins.lifecycle import PluginLifecycle
from ugaf.sdk.context import GameContext
from ugaf.sdk.events import (
    PLUGIN_FAILED,
    PLUGIN_INITIALIZED,
    PLUGIN_PAUSED,
    PLUGIN_SHUTDOWN,
    PLUGIN_STARTED,
    PLUGIN_STOPPED,
)
from ugaf.sdk.exceptions import PluginStateError
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState

pytestmark = pytest.mark.asyncio


_SIMPLE_META = PluginMetadata(
    name="Simple",
    id="simple",
    author="Test",
    version="1.0.0",
)


class _TrackingPlugin(GamePlugin):
    metadata = _SIMPLE_META

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail_on: str | None = None

    async def initialize(self, context: GameContext) -> None:
        self.calls.append("initialize")
        if self.fail_on == "initialize":
            raise RuntimeError("init fail")

    async def start(self) -> None:
        self.calls.append("start")
        if self.fail_on == "start":
            raise RuntimeError("start fail")

    async def pause(self) -> None:
        self.calls.append("pause")
        if self.fail_on == "pause":
            raise RuntimeError("pause fail")

    async def resume(self) -> None:
        self.calls.append("resume")
        if self.fail_on == "resume":
            raise RuntimeError("resume fail")

    async def stop(self) -> None:
        self.calls.append("stop")
        if self.fail_on == "stop":
            raise RuntimeError("stop fail")

    async def shutdown(self) -> None:
        self.calls.append("shutdown")
        if self.fail_on == "shutdown":
            raise RuntimeError("shutdown fail")

    async def health(self) -> dict[str, Any]:
        return {"status": "ok"}


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def context() -> GameContext:
    return GameContext(config={}, logger=None, event_bus=EventBus())


class TestPluginLifecycle:
    async def test_initial_state(self, event_bus: EventBus) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        assert lc.state is GameState.CREATED
        assert lc.plugin is plugin
        assert lc.metadata is _SIMPLE_META

    async def test_full_lifecycle(self, event_bus: EventBus, context: GameContext) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)

        await lc.initialize(context)
        assert lc.state.value == "initialized"
        assert "initialize" in plugin.calls

        await lc.start()
        assert lc.state.value == "running"
        assert "start" in plugin.calls

        await lc.pause()
        assert lc.state.value == "paused"  # type: ignore[comparison-overlap]
        assert "pause" in plugin.calls

        await lc.resume()
        assert lc.state.value == "running"
        assert "resume" in plugin.calls

        await lc.stop()
        assert lc.state.value == "stopped"
        assert "stop" in plugin.calls

        await lc.shutdown()
        assert lc.state.value == "shutdown"
        assert "shutdown" in plugin.calls

    async def test_initialize_publishes_event(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_INITIALIZED, _handler)
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)

        assert len(received) == 1
        assert received[0].topic == PLUGIN_INITIALIZED
        assert received[0].data["plugin_id"] == "simple"

    async def test_start_publishes_event(self, event_bus: EventBus, context: GameContext) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_STARTED, _handler)
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.start()

        assert len(received) == 1
        assert received[0].topic == PLUGIN_STARTED

    async def test_pause_publishes_event(self, event_bus: EventBus, context: GameContext) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_PAUSED, _handler)
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.start()
        await lc.pause()

        assert len(received) == 1
        assert received[0].topic == PLUGIN_PAUSED

    async def test_stop_publishes_event(self, event_bus: EventBus, context: GameContext) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_STOPPED, _handler)
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.start()
        await lc.stop()

        assert len(received) == 1
        assert received[0].topic == PLUGIN_STOPPED

    async def test_shutdown_publishes_event(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_SHUTDOWN, _handler)
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.shutdown()

        assert len(received) == 1
        assert received[0].topic == PLUGIN_SHUTDOWN

    async def test_health(self, event_bus: EventBus) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        result = await lc.health()
        assert result["status"] == "ok"
        assert result["state"] == "created"

    async def test_health_includes_state(self, event_bus: EventBus, context: GameContext) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        result = await lc.health()
        assert result["state"] == "initialized"

    async def test_health_handles_exception(self, event_bus: EventBus) -> None:
        class _FailingPlugin(GamePlugin):
            metadata = _SIMPLE_META

            async def initialize(self, ctx: GameContext) -> None: ...
            async def start(self) -> None: ...
            async def pause(self) -> None: ...
            async def resume(self) -> None: ...
            async def stop(self) -> None: ...
            async def shutdown(self) -> None: ...

            async def health(self) -> dict[str, Any]:
                raise RuntimeError("health fail")

        plugin = _FailingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        result = await lc.health()
        assert result["status"] == "error"
        assert "health fail" in result.get("error", "")

    async def test_invalid_transition_raises(self, event_bus: EventBus) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        with pytest.raises(PluginStateError, match="Cannot transition"):
            await lc.start()

    async def test_shutdown_twice_raises(self, event_bus: EventBus, context: GameContext) -> None:
        plugin = _TrackingPlugin()
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.shutdown()
        with pytest.raises(PluginStateError, match="already shut down"):
            await lc.shutdown()

    async def test_initialize_failure_sets_error_state(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        plugin = _TrackingPlugin()
        plugin.fail_on = "initialize"
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        with pytest.raises(RuntimeError, match="init fail"):
            await lc.initialize(context)
        assert lc.state is GameState.ERROR

    async def test_initialize_failure_publishes_failed_event(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_FAILED, _handler)
        plugin = _TrackingPlugin()
        plugin.fail_on = "initialize"
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        with pytest.raises(RuntimeError):
            await lc.initialize(context)

        assert any(e.topic == PLUGIN_FAILED for e in received)
        failed = [e for e in received if e.topic == PLUGIN_FAILED]
        assert failed[0].data["operation"] == "initialize"

    async def test_start_failure_sets_error_state(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        plugin = _TrackingPlugin()
        plugin.fail_on = "start"
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        with pytest.raises(RuntimeError, match="start fail"):
            await lc.start()
        assert lc.state is GameState.ERROR

    async def test_stop_failure_sets_error_state(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        plugin = _TrackingPlugin()
        plugin.fail_on = "stop"
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.start()
        with pytest.raises(RuntimeError, match="stop fail"):
            await lc.stop()
        assert lc.state is GameState.ERROR

    async def test_shutdown_error_does_not_prevent_state_change(
        self, event_bus: EventBus, context: GameContext
    ) -> None:
        plugin = _TrackingPlugin()
        plugin.fail_on = "shutdown"
        lc = PluginLifecycle(plugin, _SIMPLE_META, event_bus)
        await lc.initialize(context)
        await lc.shutdown()
        assert lc.state is GameState.SHUTDOWN
