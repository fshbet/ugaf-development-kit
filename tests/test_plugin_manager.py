"""Tests for the PluginManager."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.test_plugin_lifecycle import _SIMPLE_META, _TrackingPlugin
from ugaf.core.config import Config
from ugaf.core.event_bus import Event, EventBus
from ugaf.plugins.manager import PluginManager
from ugaf.sdk.events import PLUGIN_LOADED
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.state import GameState

pytestmark = pytest.mark.asyncio


@pytest.fixture
def config() -> Config:
    return Config()


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def manager(config: Config, event_bus: EventBus) -> PluginManager:
    return PluginManager(
        config=config,
        event_bus=event_bus,
        games_dir=Path("nonexistent"),
    )


class TestPluginManager:
    async def test_initial_state(self, manager: PluginManager) -> None:
        assert manager.registry.count == 0
        assert manager.lifecycles == {}
        assert manager.context is None

    async def test_discover_empty_dir(self, tmp_path: Path) -> None:
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        result = mgr.discover()
        assert result == []

    async def test_discover_loads_plugin(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "test_game")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        result = mgr.discover()
        assert len(result) == 1
        assert result[0].id == "test_game"

    async def test_discover_skips_duplicate(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "same_id")
        _create_test_plugin(tmp_path, "same_id")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        result = mgr.discover()
        assert len(result) == 1

    async def test_discover_publishes_loaded_events(
        self, tmp_path: Path, event_bus: EventBus
    ) -> None:
        received: list[Event] = []

        async def _handler(event: Event) -> None:
            received.append(event)

        await event_bus.subscribe(PLUGIN_LOADED, _handler)
        _create_test_plugin(tmp_path, "test_game")
        mgr = PluginManager(config=Config(), event_bus=event_bus, games_dir=tmp_path)
        mgr.discover()
        await asyncio.sleep(0)
        assert len(received) >= 1
        assert any(e.topic == PLUGIN_LOADED for e in received)

    # ------------------------------------------------------------------
    # load()
    # ------------------------------------------------------------------

    async def test_load_creates_lifecycle(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        lc = manager.load("simple")
        assert lc.metadata.id == "simple"
        assert lc.state.value == "created"

    async def test_load_twice_returns_same(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        lc1 = manager.load("simple")
        lc2 = manager.load("simple")
        assert lc1 is lc2

    async def test_load_unknown_raises(self, manager: PluginManager) -> None:
        with pytest.raises(KeyError, match="not registered"):
            manager.load("nonexistent")

    # ------------------------------------------------------------------
    # Individual lifecycle
    # ------------------------------------------------------------------

    async def test_initialize(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        await manager.initialize("simple")
        assert manager._lifecycles["simple"].state.value == "initialized"

    async def test_start(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        await manager.initialize("simple")
        await manager.start("simple")
        assert manager._lifecycles["simple"].state.value == "running"

    async def test_full_individual_lifecycle(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        await manager.initialize("simple")
        await manager.start("simple")
        await manager.pause("simple")
        assert manager._lifecycles["simple"].state.value == "paused"
        await manager.resume("simple")
        assert manager._lifecycles["simple"].state.value == "running"
        await manager.stop("simple")
        assert manager._lifecycles["simple"].state == GameState.STOPPED
        await manager.shutdown("simple")
        assert manager._lifecycles["simple"].state == GameState.SHUTDOWN  # type: ignore[comparison-overlap]

    async def test_health(self, manager: PluginManager) -> None:
        manager._registry.register(_SIMPLE_META, _TrackingPlugin)
        result = await manager.health("simple")
        assert result["state"] == "created"

    # ------------------------------------------------------------------
    # All-at-once lifecycle
    # ------------------------------------------------------------------

    async def test_initialize_all(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "game_a")
        _create_test_plugin(tmp_path, "game_b")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        mgr.discover()
        mgr.load("game_a")
        mgr.load("game_b")
        await mgr.initialize_all()
        assert mgr._lifecycles["game_a"].state.value == "initialized"
        assert mgr._lifecycles["game_b"].state.value == "initialized"

    async def test_start_all(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "game_a")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        mgr.discover()
        mgr.load("game_a")
        await mgr.initialize_all()
        await mgr.start_all()
        assert mgr._lifecycles["game_a"].state.value == "running"

    async def test_stop_all(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "game_a")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        mgr.discover()
        mgr.load("game_a")
        await mgr.initialize_all()
        await mgr.start_all()
        await mgr.stop_all()
        assert mgr._lifecycles["game_a"].state.value == "stopped"

    async def test_shutdown_all(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "game_a")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        mgr.discover()
        mgr.load("game_a")
        await mgr.initialize_all()
        await mgr.shutdown_all()
        assert mgr._lifecycles["game_a"].state.value == "shutdown"

    # ------------------------------------------------------------------
    # Full lifecycle
    # ------------------------------------------------------------------

    async def test_full_discover_to_shutdown(self, tmp_path: Path) -> None:
        _create_test_plugin(tmp_path, "full_test")
        mgr = PluginManager(config=Config(), games_dir=tmp_path)
        mgr.discover()
        mgr.load("full_test")
        await mgr.initialize_all()
        await mgr.start_all()
        await mgr.pause_all()
        await mgr.resume_all()
        await mgr.stop_all()
        await mgr.shutdown_all()
        lc = mgr._lifecycles["full_test"]
        assert lc.state.value == "shutdown"

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    async def test_initialize_failure(self, manager: PluginManager) -> None:
        class _FailingPlugin(GamePlugin):
            metadata = _SIMPLE_META

            async def initialize(self, ctx: Any) -> None:
                raise RuntimeError("fail")

            async def start(self) -> None: ...
            async def pause(self) -> None: ...
            async def resume(self) -> None: ...
            async def stop(self) -> None: ...
            async def shutdown(self) -> None: ...
            async def health(self) -> dict[str, Any]:
                return {"status": "ok"}

        manager._registry.register(_SIMPLE_META, _FailingPlugin)
        with pytest.raises(RuntimeError, match="fail"):
            await manager.initialize("simple")
        assert manager._lifecycles["simple"].state.value == "error"


class TestScreenshotIntegration:
    """A plugin resolves ScreenshotManager/VisionManager with real screen capture."""

    async def test_vision_screenshot_works_when_provider_configured(
        self, event_bus: EventBus
    ) -> None:
        from ugaf.core.config import Config
        from ugaf.vision.manager import VisionManager

        cfg = Config()
        cfg._data = {"vision": {"screenshot_provider": "mock"}}
        manager = PluginManager(
            config=cfg,
            event_bus=event_bus,
            games_dir=Path("nonexistent"),
        )

        context = manager._get_or_create_context()
        vision = context.service_container.resolve(VisionManager)
        frame = vision.screenshot()
        assert frame.size.width == 1080

    async def test_vision_screenshot_raises_when_no_provider_configured(
        self, manager: PluginManager
    ) -> None:
        from ugaf.vision.exceptions import ScreenshotError
        from ugaf.vision.manager import VisionManager

        context = manager._get_or_create_context()
        vision = context.service_container.resolve(VisionManager)
        with pytest.raises(ScreenshotError):
            vision.screenshot()


class TestDeviceManagerIntegration:
    """A plugin resolves DeviceManager from its GameContext to build per-device input."""

    async def test_device_manager_resolvable_from_context(
        self, config: Config, event_bus: EventBus
    ) -> None:
        from ugaf.device.manager import DeviceManager

        device_manager = DeviceManager()
        manager = PluginManager(
            config=config,
            event_bus=event_bus,
            games_dir=Path("nonexistent"),
            device_manager=device_manager,
        )

        context = manager._get_or_create_context()
        resolved = context.service_container.resolve(DeviceManager)
        assert resolved is device_manager

    async def test_context_without_device_manager_does_not_register_it(
        self, manager: PluginManager
    ) -> None:
        from ugaf.core.di import DependencyInjectionError
        from ugaf.device.manager import DeviceManager

        context = manager._get_or_create_context()
        with pytest.raises(DependencyInjectionError):
            context.service_container.resolve(DeviceManager)


def _create_test_plugin(base_dir: Path, plugin_id: str) -> None:
    """Create a minimal valid plugin directory for testing."""
    plugin_dir = base_dir / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": plugin_id.replace("_", " ").title(),
        "id": plugin_id,
        "author": "Test",
        "version": "1.0.0",
    }
    (plugin_dir / "manifest.yaml").write_text(yaml.dump(manifest))

    (plugin_dir / "plugin.py").write_text(f"""
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.context import GameContext
from ugaf.sdk.metadata import PluginMetadata

class _{plugin_id.title().replace("_", "")}(GamePlugin):
    metadata = PluginMetadata(
        name="{manifest["name"]}", id="{plugin_id}", author="Test", version="1.0.0"
    )

    async def initialize(self, ctx: GameContext) -> None: ...
    async def start(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health(self) -> dict: return {{"status": "ok"}}
""")
