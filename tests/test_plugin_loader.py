"""Tests for the Plugin Loader module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ugaf.core.event_bus import EventBus
from ugaf.core.plugin_loader import (
    PluginLoader,
    PluginLoaderError,
    PluginManifest,
)


def _create_plugin(
    base_dir: Path,
    name: str,
    version: str = "1.0.0",
    with_bot: bool = False,
    with_vision: bool = False,
    with_strategy: bool = False,
    with_config: bool = False,
) -> Path:
    """Create a minimal plugin directory structure."""
    plugin_dir = base_dir / name
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {"name": name, "version": version}
    (plugin_dir / "manifest.yaml").write_text(yaml.dump(manifest))

    if with_bot:
        (plugin_dir / "bot.py").write_text("# bot module")
    if with_vision:
        (plugin_dir / "vision.py").write_text("# vision module")
    if with_strategy:
        (plugin_dir / "strategy.py").write_text("# strategy module")
    if with_config:
        (plugin_dir / "config.yaml").write_text(
            yaml.dump({"enabled": True, "settings": {"key": "value"}})
        )

    return plugin_dir


def test_discover_no_games_dir(tmp_path: Path) -> None:
    nonexistent = tmp_path / "nonexistent"
    loader = PluginLoader(nonexistent)
    with pytest.raises(PluginLoaderError, match="not found"):
        loader.discover()


def test_discover_empty_dir(tmp_path: Path) -> None:
    games = tmp_path / "games"
    games.mkdir()
    loader = PluginLoader(games)
    plugins = loader.discover()
    assert plugins == []


def test_discover_single_plugin(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "TestGame")
    loader = PluginLoader(tmp_path)
    plugins = loader.discover()

    assert len(plugins) == 1
    assert plugins[0].manifest.name == "TestGame"
    assert plugins[0].manifest.version == "1.0.0"


def test_discover_multiple_plugins(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "GameA")
    _create_plugin(tmp_path, "GameB", version="2.0.0")
    loader = PluginLoader(tmp_path)
    plugins = loader.discover()

    assert len(plugins) == 2
    names = {p.manifest.name for p in plugins}
    assert names == {"GameA", "GameB"}


def test_skip_directories_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "no_manifest").mkdir()
    _create_plugin(tmp_path, "ValidGame")
    loader = PluginLoader(tmp_path)
    plugins = loader.discover()
    assert len(plugins) == 1
    assert plugins[0].manifest.name == "ValidGame"


def test_parse_manifest(tmp_path: Path) -> None:
    plugin_dir = _create_plugin(tmp_path, "MyGame", version="0.5.0")
    loader = PluginLoader(tmp_path)
    manifest = loader._parse_manifest(plugin_dir / "manifest.yaml")
    assert isinstance(manifest, PluginManifest)
    assert manifest.name == "MyGame"
    assert manifest.version == "0.5.0"


def test_parse_manifest_missing_file(tmp_path: Path) -> None:
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="Failed to read"):
        loader._parse_manifest(tmp_path / "missing.yaml")


def test_load_config_exists(tmp_path: Path) -> None:
    plugin_dir = _create_plugin(tmp_path, "CfgGame", with_config=True)
    loader = PluginLoader(tmp_path)
    config = loader._load_config(plugin_dir / "config.yaml")
    assert config == {"enabled": True, "settings": {"key": "value"}}


def test_load_config_missing(tmp_path: Path) -> None:
    loader = PluginLoader(tmp_path)
    config = loader._load_config(tmp_path / "nonexistent.yaml")
    assert config == {}


def test_import_module(tmp_path: Path) -> None:
    plugin_dir = _create_plugin(tmp_path, "ModGame", with_bot=True)
    loader = PluginLoader(tmp_path)
    module = loader._import_module(plugin_dir, "bot")
    assert module is not None
    assert hasattr(module, "__file__")


def test_import_module_missing(tmp_path: Path) -> None:
    loader = PluginLoader(tmp_path)
    module = loader._import_module(tmp_path, "nonexistent")
    assert module is None


def test_get_plugin(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "FindMe")
    loader = PluginLoader(tmp_path)
    loader.discover()

    plugin = loader.get_plugin("FindMe")
    assert plugin is not None
    assert plugin.manifest.name == "FindMe"

    assert loader.get_plugin("DoesNotExist") is None


def test_plugins_property(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "Alpha")
    _create_plugin(tmp_path, "Beta")
    loader = PluginLoader(tmp_path)
    loader.discover()

    plugins = loader.plugins
    assert set(plugins.keys()) == {"Alpha", "Beta"}


@pytest.mark.asyncio
async def test_start_stop_events(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "EventGame")
    loader = PluginLoader(tmp_path)
    loader.discover()

    bus = EventBus()
    events: list[str] = []

    async def tracker(event):  # type: ignore[no-untyped-def]
        events.append(event.topic)

    await bus.subscribe("plugin.*", tracker)
    await loader.start_all(bus)

    assert "plugin.started" in events
    assert loader.get_plugin("EventGame") is not None
    assert loader.get_plugin("EventGame").started is True  # type: ignore[union-attr]

    await loader.stop_all(bus)
    assert "plugin.stopped" in events
    assert loader.get_plugin("EventGame").started is False  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_start_only_unstarted(tmp_path: Path) -> None:
    _create_plugin(tmp_path, "Dual")
    loader = PluginLoader(tmp_path)
    loader.discover()

    bus = EventBus()
    events: list[str] = []

    async def tracker(event):  # type: ignore[no-untyped-def]
        events.append(event.topic)

    await bus.subscribe("plugin.*", tracker)
    await loader.start_all(bus)
    await loader.start_all(bus)  # second call should be no-op

    started_count = sum(1 for e in events if e == "plugin.started")
    assert started_count == 1


def test_parse_manifest_empty(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text("")
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="Empty manifest"):
        loader._parse_manifest(manifest_file)


def test_parse_manifest_missing_name(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(yaml.dump({"version": "1.0.0"}))
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="missing required field 'name'"):
        loader._parse_manifest(manifest_file)


def test_parse_manifest_missing_version(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(yaml.dump({"name": "TestGame"}))
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="missing required field 'version'"):
        loader._parse_manifest(manifest_file)


def test_parse_manifest_empty_name(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(yaml.dump({"name": "", "version": "1.0.0"}))
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="missing required field 'name'"):
        loader._parse_manifest(manifest_file)


def test_parse_manifest_none_name(tmp_path: Path) -> None:
    manifest_file = tmp_path / "manifest.yaml"
    manifest_file.write_text(yaml.dump({"name": None, "version": "1.0.0"}))
    loader = PluginLoader(tmp_path)
    with pytest.raises(PluginLoaderError, match="missing required field 'name'"):
        loader._parse_manifest(manifest_file)
