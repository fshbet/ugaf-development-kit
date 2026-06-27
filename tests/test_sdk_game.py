"""Tests for the GamePlugin abstract base class."""

from __future__ import annotations

from typing import Any

from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata


class TestGamePlugin:
    def test_abstract_cannot_instantiate(self) -> None:
        class Incomplete(GamePlugin):
            metadata = PluginMetadata(
                name="Incomplete",
                id="incomplete",
                author="Test",
                version="1.0.0",
            )

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_concrete_plugin_is_valid(self) -> None:
        plugin = _ConcretePlugin()
        assert plugin.metadata.name == "Concrete"
        assert plugin.metadata.id == "concrete"
        assert plugin.metadata.version == "1.0.0"

    async def test_lifecycle_methods(self) -> None:
        plugin = _ConcretePlugin()
        ctx = GameContext(config={}, logger=None, event_bus=None)  # type: ignore[arg-type]

        await plugin.initialize(ctx)
        assert plugin._initialized is True

        await plugin.start()
        assert plugin._started is True

        await plugin.pause()
        assert plugin._paused is True

        await plugin.resume()
        assert plugin._resumed is True

        await plugin.stop()
        assert plugin._stopped is True

        await plugin.shutdown()
        assert plugin._shutdown is True

    async def test_health(self) -> None:
        plugin = _ConcretePlugin()
        result = await plugin.health()
        assert isinstance(result, dict)
        assert result["status"] == "healthy"


class _ConcretePlugin(GamePlugin):
    """Concrete GamePlugin implementation for testing."""

    metadata = PluginMetadata(
        name="Concrete",
        id="concrete",
        author="Test",
        version="1.0.0",
    )

    def __init__(self) -> None:
        self._initialized = False
        self._started = False
        self._paused = False
        self._resumed = False
        self._stopped = False
        self._shutdown = False

    async def initialize(self, context: GameContext) -> None:
        self._initialized = True

    async def start(self) -> None:
        self._started = True

    async def pause(self) -> None:
        self._paused = True

    async def resume(self) -> None:
        self._resumed = True

    async def stop(self) -> None:
        self._stopped = True

    async def shutdown(self) -> None:
        self._shutdown = True

    async def health(self) -> dict[str, Any]:
        return {"status": "healthy"}


import pytest
