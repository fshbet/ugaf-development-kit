"""Tests for the Application bootstrap module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ugaf.core.bootstrap import Application


def _write_config(path: Path, data: dict) -> Path:  # type: ignore[type-arg]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data))
    return path


@pytest.mark.asyncio
async def test_initialize_creates_services(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "DEBUG"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()

    assert app.config is not None
    assert app.logger is not None
    assert app.event_bus is not None
    assert app.plugin_manager is not None
    assert app.device_manager is not None
    assert app.config.get("logging.level") == "DEBUG"


@pytest.mark.asyncio
async def test_initialize_raises_if_called_twice(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()

    with pytest.raises(RuntimeError, match="already initialized"):
        await app.initialize()


@pytest.mark.asyncio
async def test_start_publishes_events(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    assert app.event_bus is not None

    events: list[str] = []

    async def tracker(event):  # type: ignore[no-untyped-def]
        events.append(event.topic)

    await app.event_bus.subscribe("app.**", tracker)
    await app.start()

    assert "app.starting" in events
    assert "app.started" in events
    assert app.is_running is True


@pytest.mark.asyncio
async def test_stop_publishes_events(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    await app.start()
    assert app.event_bus is not None

    events: list[str] = []

    async def tracker(event):  # type: ignore[no-untyped-def]
        events.append(event.topic)

    await app.event_bus.subscribe("app.**", tracker)
    await app.stop()

    assert "app.stopping" in events
    assert "app.stopped" in events
    assert app.is_running is False


@pytest.mark.asyncio
async def test_start_raises_if_not_initialized(tmp_path: Path) -> None:
    app = Application()
    with pytest.raises(RuntimeError, match="initialize"):
        await app.start()


@pytest.mark.asyncio
async def test_stop_raises_if_not_initialized(tmp_path: Path) -> None:
    app = Application()
    with pytest.raises(RuntimeError, match="not initialized"):
        await app.stop()


@pytest.mark.asyncio
async def test_stop_without_start(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()

    # Should not raise even though start() was never called
    await app.stop()
    assert app.is_running is False


@pytest.mark.asyncio
async def test_start_without_auto_start_plugins_only_discovers(tmp_path: Path) -> None:
    """The web control panel needs plugins discovered but not auto-started."""
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    app = Application(config_path=config_path, games_dir=Path("games"))
    await app.initialize()
    await app.start(auto_start_plugins=False)

    assert app.plugin_manager is not None
    assert len(app.plugin_manager.registry.list()) > 0  # discovered
    assert app.plugin_manager.lifecycles == {}  # but nothing initialized/started

    await app.stop()


@pytest.mark.asyncio
async def test_start_with_device_monitoring_enabled(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {
            "logging": {"level": "INFO"},
            "device": {"monitor": {"enabled": True, "interval": 0.01}},
        },
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    await app.start()
    assert app.device_manager is not None
    assert app.device_manager._monitor_task is not None

    await app.stop()
    assert app.device_manager._monitor_task is None


@pytest.mark.asyncio
async def test_health_reports_all_components(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    results = await app.health()

    components = {r.component for r in results}
    assert components == {"config", "event_bus", "plugin_manager", "device_manager"}
    assert all(r.status.value == "healthy" for r in results)


@pytest.mark.asyncio
async def test_context_property_includes_device_manager(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "config.yaml",
        {"logging": {"level": "INFO"}},
    )
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    context = app.context
    assert context.device_manager is app.device_manager


@pytest.mark.asyncio
async def test_default_paths_used_when_not_provided(tmp_path: Path) -> None:
    # The default config path is config/default.yaml
    app = Application()
    assert app._config_path == Path("config/default.yaml")
    assert app._games_dir == Path("games")
