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
from ugaf.core.bootstrap import Application
from ugaf.input.manager import InputManager

_SCREEN_SIZE = (1080, 2400)


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
