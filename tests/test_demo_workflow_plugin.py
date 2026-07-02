"""End-to-end test for the demo_workflow plugin.

This is the automated form of the Version 0.1 demonstration: capture
the screen, find a template, tap it, swipe, enter text — driven
through the real `Application`/`PluginManager` discovery path against
the real bundled demo assets (not mocks of the plugin itself).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ugaf.core.bootstrap import Application

pytestmark = pytest.mark.asyncio


async def test_demo_workflow_runs_end_to_end() -> None:
    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    await app.start()
    try:
        health = await app.plugin_manager.health("demo_workflow")
    finally:
        await app.stop()

    assert health["status"] == "completed"
    result = health["last_result"]
    assert result["captured"] is True
    assert result["match_confidence"] > 0.99
    assert result["match_region"] == "Region(x=460, y=900, width=160, height=70)"
    assert result["tapped"] == (540, 935)


async def test_demo_workflow_is_discoverable_with_correct_metadata() -> None:
    app = Application(config_path=Path("config/default.yaml"), games_dir=Path("games"))
    await app.initialize()
    discovered = app.plugin_manager.discover()

    demo = next(m for m in discovered if m.id == "demo_workflow")
    assert demo.name == "Demo Workflow"
    assert demo.version == "1.0.0"
