"""Tests for the PluginLoader."""

from __future__ import annotations

from pathlib import Path

import yaml

from ugaf.plugins.loader import PluginLoader


class TestPluginLoader:
    def test_discover_no_games_dir(self, tmp_path: Path) -> None:
        loader = PluginLoader(tmp_path / "nonexistent")
        result = loader.discover()
        assert result == []

    def test_discover_empty_dir(self, tmp_path: Path) -> None:
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert result == []

    def test_discover_skips_non_directories(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert result == []

    def test_discover_skips_without_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "no_manifest"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text("from ugaf.sdk.game import GamePlugin\n")
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert result == []

    def test_discover_skips_without_plugin_py(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "no_plugin_py"
        plugin_dir.mkdir()
        _write_manifest(
            plugin_dir,
            {"name": "NoCode", "id": "nocode", "author": "T", "version": "1.0.0"},
        )
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert result == []

    def test_discover_skips_invalid_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "bad_manifest"
        plugin_dir.mkdir()
        (plugin_dir / "manifest.yaml").write_text("{invalid_yaml: [}")
        (plugin_dir / "plugin.py").write_text("")
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert result == []

    def test_discover_loads_valid_plugin(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "valid_game"
        plugin_dir.mkdir()
        _write_manifest(
            plugin_dir,
            {
                "name": "Valid Game",
                "id": "valid_game",
                "author": "Tester",
                "version": "1.0.0",
            },
        )
        (plugin_dir / "plugin.py").write_text("""
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.context import GameContext
from ugaf.sdk.metadata import PluginMetadata

class ValidGame(GamePlugin):
    metadata = PluginMetadata(name="Valid Game", id="valid_game", author="Tester", version="1.0.0")

    async def initialize(self, ctx: GameContext) -> None: ...
    async def start(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health(self) -> dict: return {"status": "ok"}
""")
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert len(result) == 1
        metadata, plugin_cls = result[0]
        assert metadata.name == "Valid Game"
        assert metadata.id == "valid_game"
        assert plugin_cls.__name__ == "ValidGame"

    def test_discover_loads_multiple_plugins(self, tmp_path: Path) -> None:
        for i in range(3):
            d = tmp_path / f"game_{i}"
            d.mkdir()
            _write_manifest(
                d,
                {
                    "name": f"Game {i}",
                    "id": f"game_{i}",
                    "author": "T",
                    "version": "1.0.0",
                },
            )
            (d / "plugin.py").write_text(f"""
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.context import GameContext
from ugaf.sdk.metadata import PluginMetadata

class Game{i}(GamePlugin):
    metadata = PluginMetadata(name="Game {i}", id="game_{i}", author="T", version="1.0.0")

    async def initialize(self, ctx: GameContext) -> None: ...
    async def start(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health(self) -> dict: return {{"status": "ok"}}
""")
        loader = PluginLoader(tmp_path)
        result = loader.discover()
        assert len(result) == 3
        ids = {r[0].id for r in result}
        assert ids == {"game_0", "game_1", "game_2"}


def _write_manifest(directory: Path, data: dict[str, object]) -> None:
    (directory / "manifest.yaml").write_text(yaml.dump(data))
