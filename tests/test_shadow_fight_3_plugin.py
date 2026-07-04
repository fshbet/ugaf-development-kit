"""Tests for the (knowledge-driven) shadow_fight_3 plugin.

The plugin itself is now a thin shell: it loads a
``KnowledgeBase``/``Strategy`` from YAML and drives an ``Executor``
loop. Move/coordinate math is exercised by
``tests/test_automation_*.py`` against the reusable
``ugaf.automation`` modules directly; these tests focus on the
plugin's own wiring — discovery, knowledge/strategy loading, and the
full lifecycle driven through the real ``PluginManager`` path (per
repo convention) with ``InputManager`` stubbed out (Shadow Fight 3 has
no mock/replay mode — real ADB device only).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from games.shadow_fight_3.plugin import ShadowFight3Game
from ugaf.apps.manager import ApplicationManager
from ugaf.apps.types import AppDefinition, LaunchResult
from ugaf.core.bootstrap import Application
from ugaf.device.manager import DeviceManager
from ugaf.input.manager import InputManager

_SCREEN_SIZE = (1080, 2400)
_DEVICE_ID = "test-device"


def _stub_successful_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass real ADB for device resolution and the app-launch workflow.

    Shadow Fight 3 has no mock mode, so plugin-lifecycle tests stub the
    two real-hardware touchpoints (which device to target, whether the
    app launched) and let everything else — knowledge loading, strategy
    selection, the executor loop — run for real.
    """

    async def fake_launch_and_wait(
        self: ApplicationManager, device_id: str, app: AppDefinition
    ) -> LaunchResult:
        return LaunchResult(
            success=True,
            package=app.package,
            foreground_package=app.package,
            attempts=1,
            elapsed=0.01,
        )

    monkeypatch.setattr(DeviceManager, "resolve_device", lambda self, configured=None: _DEVICE_ID)
    monkeypatch.setattr(ApplicationManager, "launch_and_wait", fake_launch_and_wait)


@pytest.mark.asyncio
async def test_shadow_fight_3_is_discoverable_with_correct_metadata() -> None:
    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    discovered = app.plugin_manager.discover()

    plugin = next(m for m in discovered if m.id == "shadow_fight_3")
    assert plugin.name == "Shadow Fight 3"
    assert plugin.supported_platforms == ["android"]


def test_plugin_loads_its_knowledge_base_on_construction() -> None:
    game = ShadowFight3Game()
    assert "jab_combo" in game._knowledge.moves
    assert "shadow_burst" in game._knowledge.moves
    assert "punch" in game._knowledge.controls.buttons
    assert game._knowledge.controls.joystick_center is not None


def test_plugin_config_selects_the_balanced_strategy_by_default() -> None:
    game = ShadowFight3Game()
    assert game._config.get("strategy") == "balanced"


@pytest.mark.asyncio
async def test_combat_loop_runs_and_stops_cleanly_via_plugin_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clicks: list[tuple[int, int]] = []

    def fake_connect(self: InputManager) -> None:  # type: ignore[no-untyped-def]
        self._screen_size = _SCREEN_SIZE

    def fake_click(self: InputManager, x: int, y: int, button: str = "left") -> None:  # type: ignore[no-untyped-def]
        clicks.append((x, y))

    monkeypatch.setattr(InputManager, "connect", fake_connect)
    monkeypatch.setattr(InputManager, "click", fake_click)
    monkeypatch.setattr(InputManager, "disconnect", lambda self: None)  # type: ignore[misc]
    _stub_successful_launch(monkeypatch)

    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    await app.start(auto_start_plugins=False)
    manager = app.plugin_manager
    assert manager is not None

    try:
        lifecycle = manager.load("shadow_fight_3")
        game = lifecycle.plugin
        # The plugin loader imports plugin.py under a synthetic module
        # name (see PluginLoader), so this is a distinct class object
        # from the one imported above despite identical source — check
        # by name rather than isinstance().
        assert type(game).__name__ == "ShadowFight3Game"
        game._config._data["max_cycles"] = None
        # Speed up the loop for the test: the balanced strategy's
        # cycle_interval is loaded fresh in start(), so patch Strategy
        # itself is unnecessary — instead shrink it after start() below.

        await manager.initialize("shadow_fight_3")
        await manager.start("shadow_fight_3")
        assert game._loop_task is not None
        assert game._strategy_engine is not None
        game._strategy_engine._strategy.cycle_interval = 0.01

        await asyncio.sleep(0.3)
        health = await manager.health("shadow_fight_3")
        assert health["status"] == "running"
        assert health["cycles_run"] > 0
        assert health["strategy"] == "balanced"
        assert health["target_app"]["package"] == "com.nekki.shadowfight3"
        assert health["target_app"]["launched"] is True
        assert len(clicks) > 0

        await manager.pause("shadow_fight_3")
        assert (await manager.health("shadow_fight_3"))["status"] == "paused"
        await manager.resume("shadow_fight_3")
        assert (await manager.health("shadow_fight_3"))["status"] == "running"

        await manager.stop("shadow_fight_3")
        assert (await manager.health("shadow_fight_3"))["status"] == "stopped"
        assert game._loop_task is None
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_switching_strategy_via_config_changes_reported_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_connect(self: InputManager) -> None:  # type: ignore[no-untyped-def]
        self._screen_size = _SCREEN_SIZE

    monkeypatch.setattr(InputManager, "connect", fake_connect)
    monkeypatch.setattr(InputManager, "click", lambda self, x, y, button="left": None)
    monkeypatch.setattr(InputManager, "disconnect", lambda self: None)  # type: ignore[misc]
    _stub_successful_launch(monkeypatch)

    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    await app.start(auto_start_plugins=False)
    manager = app.plugin_manager
    assert manager is not None

    try:
        lifecycle = manager.load("shadow_fight_3")
        game = lifecycle.plugin
        game._config._data["strategy"] = "aggressive"
        game._config._data["max_cycles"] = 1

        await manager.initialize("shadow_fight_3")
        await manager.start("shadow_fight_3")
        assert game._strategy_engine is not None
        assert game._strategy_engine.name == "aggressive"

        await manager.stop("shadow_fight_3")
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_start_raises_and_never_connects_input_when_app_launch_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Automation must never begin if the target app never reaches the foreground."""
    connect_calls: list[None] = []

    async def fake_launch_and_wait(
        self: ApplicationManager, device_id: str, app: AppDefinition
    ) -> LaunchResult:
        return LaunchResult(
            success=False,
            package=app.package,
            foreground_package=None,
            attempts=3,
            elapsed=1.0,
            error="not installed",
        )

    monkeypatch.setattr(DeviceManager, "resolve_device", lambda self, configured=None: _DEVICE_ID)
    monkeypatch.setattr(ApplicationManager, "launch_and_wait", fake_launch_and_wait)
    monkeypatch.setattr(
        InputManager, "connect", lambda self: connect_calls.append(None)  # type: ignore[func-returns-value]
    )

    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    await app.start(auto_start_plugins=False)
    manager = app.plugin_manager
    assert manager is not None

    try:
        await manager.initialize("shadow_fight_3")
        with pytest.raises(Exception, match="not ready"):
            await manager.start("shadow_fight_3")
        assert connect_calls == []
    finally:
        await app.stop()


@pytest.mark.asyncio
async def test_two_concurrent_device_bound_instances_run_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same automation runs on two devices at once, each with its own state.

    Exercises PluginManager's device_id-parametrized lifecycle against
    the real ShadowFight3Game (not a dummy plugin, unlike
    test_plugin_manager_multidevice.py's generic coverage) — the
    plugin's own device resolution must prefer the per-instance
    context.device_id over its config/resolve_device() fallback.
    """
    clicks: dict[str, list[tuple[int, int]]] = {"deviceA": [], "deviceB": []}
    connected_devices: list[str] = []

    def fake_connect(self: InputManager) -> None:  # type: ignore[no-untyped-def]
        self._screen_size = _SCREEN_SIZE
        connected_devices.append(self._device_id)

    def fake_click(self: InputManager, x: int, y: int, button: str = "left") -> None:  # type: ignore[no-untyped-def]
        assert self._device_id is not None
        clicks[self._device_id].append((x, y))

    monkeypatch.setattr(InputManager, "connect", fake_connect)
    monkeypatch.setattr(InputManager, "click", fake_click)
    monkeypatch.setattr(InputManager, "disconnect", lambda self: None)  # type: ignore[misc]
    _stub_successful_launch(monkeypatch)

    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    await app.start(auto_start_plugins=False)
    manager = app.plugin_manager
    assert manager is not None

    try:
        await manager.initialize("shadow_fight_3", device_id="deviceA")
        await manager.initialize("shadow_fight_3", device_id="deviceB")

        game_a = manager.lifecycles["shadow_fight_3@deviceA"].plugin
        game_b = manager.lifecycles["shadow_fight_3@deviceB"].plugin
        assert game_a is not game_b

        await asyncio.gather(
            manager.start("shadow_fight_3", device_id="deviceA"),
            manager.start("shadow_fight_3", device_id="deviceB"),
        )
        assert sorted(connected_devices) == ["deviceA", "deviceB"]

        assert manager.lifecycles["shadow_fight_3@deviceA"].plugin._strategy_engine is not None
        assert manager.lifecycles["shadow_fight_3@deviceB"].plugin._strategy_engine is not None
        for key in ("shadow_fight_3@deviceA", "shadow_fight_3@deviceB"):
            manager.lifecycles[key].plugin._strategy_engine._strategy.cycle_interval = 0.01

        await asyncio.sleep(0.3)

        health_a = await manager.health("shadow_fight_3", device_id="deviceA")
        health_b = await manager.health("shadow_fight_3", device_id="deviceB")
        assert health_a["status"] == "running"
        assert health_b["status"] == "running"
        assert health_a["cycles_run"] > 0
        assert health_b["cycles_run"] > 0
        # Each instance really did tap its own device, not the other's.
        assert len(clicks["deviceA"]) > 0
        assert len(clicks["deviceB"]) > 0

        await asyncio.gather(
            manager.stop("shadow_fight_3", device_id="deviceA"),
            manager.stop("shadow_fight_3", device_id="deviceB"),
        )
        assert (await manager.health("shadow_fight_3", device_id="deviceA"))["status"] == "stopped"
        assert (await manager.health("shadow_fight_3", device_id="deviceB"))["status"] == "stopped"
    finally:
        await app.stop()
