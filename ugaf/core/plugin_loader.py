"""Plugin discovery and loading from the games directory."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from ugaf.core.event_bus import Event, EventBus
from ugaf.core.exceptions import PluginLoaderError
from ugaf.core.logger import Logger, get_logger

__all__ = [
    "PluginInfo",
    "PluginLoader",
    "PluginLoaderError",
    "PluginManifest",
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PluginManifest:
    """Plugin manifest parsed from ``manifest.yaml``.

    Attributes:
        name: Human-readable game name.
        version: Semantic version string.

    """

    name: str
    version: str


@dataclass
class PluginInfo:
    """Runtime information for a loaded plugin.

    Attributes:
        manifest: Parsed plugin manifest.
        directory: Absolute path to the plugin directory.
        bot_module: Loaded ``bot.py`` module, if present.
        vision_module: Loaded ``vision.py`` module, if present.
        strategy_module: Loaded ``strategy.py`` module, if present.
        config: Plugin-specific configuration loaded from ``config.yaml``.
        started: Whether the plugin has been started.

    """

    manifest: PluginManifest
    directory: Path
    bot_module: ModuleType | None = None
    vision_module: ModuleType | None = None
    strategy_module: ModuleType | None = None
    config: dict[str, Any] = field(default_factory=dict)
    started: bool = False


# ---------------------------------------------------------------------------
# Plugin loader
# ---------------------------------------------------------------------------


class PluginLoader:
    """Discovers and loads game plugins from a designated directory.

    Each plugin is expected to live in a subdirectory containing
    ``manifest.yaml``. Optionally it may also contain ``bot.py``,
    ``vision.py``, ``strategy.py`` and ``config.yaml``.

    Usage::

        loader = PluginLoader(Path("games"))
        plugins = loader.discover()
        await loader.start_all(event_bus)
        # ...
        await loader.stop_all(event_bus)
    """

    def __init__(
        self,
        games_dir: Path | str,
        logger: Logger | None = None,
    ) -> None:
        """Initialise the plugin loader.

        Args:
            games_dir: Path to the directory containing game plugin
                subdirectories.
            logger: Optional logger instance.

        """
        self._games_dir = Path(games_dir).resolve()
        self._logger = logger or get_logger()
        self._plugins: dict[str, PluginInfo] = {}

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginInfo]:
        """Scan the games directory and return discovered plugin info.

        Returns:
            List of ``PluginInfo`` objects for each valid plugin
            directory found.

        Raises:
            PluginLoaderError: If the games directory does not exist.

        """
        if not self._games_dir.is_dir():
            raise PluginLoaderError(f"Games directory not found: {self._games_dir}")

        discovered: list[PluginInfo] = []

        for entry in sorted(self._games_dir.iterdir()):
            if not entry.is_dir():
                continue
            manifest_path = entry / "manifest.yaml"
            if not manifest_path.is_file():
                self._logger.debug(
                    "plugin_loader.skipped_no_manifest",
                    directory=str(entry),
                )
                continue

            try:
                plugin = self._load_plugin(entry)
                discovered.append(plugin)
                self._plugins[plugin.manifest.name] = plugin
                self._logger.info(
                    "plugin_loader.discovered",
                    name=plugin.manifest.name,
                    version=plugin.manifest.version,
                )
            except PluginLoaderError:
                self._logger.warning(
                    "plugin_loader.load_failed",
                    directory=str(entry),
                )

        return discovered

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self, event_bus: EventBus) -> None:
        """Call ``start()`` on every loaded plugin via the event bus.

        Publishes a ``plugin.started`` event for each plugin.

        Args:
            event_bus: The application event bus.

        """
        for name, plugin in self._plugins.items():
            if not plugin.started:
                plugin.started = True
                await event_bus.publish(
                    Event(
                        topic="plugin.started",
                        data={"name": name, "version": plugin.manifest.version},
                    )
                )
                self._logger.info(
                    "plugin_loader.started",
                    name=name,
                )

    async def stop_all(self, event_bus: EventBus) -> None:
        """Call ``stop()`` on every running plugin via the event bus.

        Publishes a ``plugin.stopped`` event for each plugin.

        Args:
            event_bus: The application event bus.

        """
        for name, plugin in list(self._plugins.items()):
            if plugin.started:
                plugin.started = False
                await event_bus.publish(
                    Event(
                        topic="plugin.stopped",
                        data={"name": name, "version": plugin.manifest.version},
                    )
                )
                self._logger.info(
                    "plugin_loader.stopped",
                    name=name,
                )

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Return plugin info by name.

        Args:
            name: Plugin name (from manifest).

        Returns:
            The ``PluginInfo`` or ``None`` if not found.

        """
        return self._plugins.get(name)

    @property
    def plugins(self) -> dict[str, PluginInfo]:
        """Return all loaded plugins keyed by name."""
        return dict(self._plugins)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_plugin(self, plugin_dir: Path) -> PluginInfo:
        """Load a single plugin from its directory.

        Args:
            plugin_dir: The plugin's directory.

        Returns:
            Populated ``PluginInfo``.

        Raises:
            PluginLoaderError: If the manifest is invalid.

        """
        manifest = self._parse_manifest(plugin_dir / "manifest.yaml")
        config = self._load_config(plugin_dir / "config.yaml")

        bot_module = self._import_module(plugin_dir, "bot")
        vision_module = self._import_module(plugin_dir, "vision")
        strategy_module = self._import_module(plugin_dir, "strategy")

        return PluginInfo(
            manifest=manifest,
            directory=plugin_dir,
            bot_module=bot_module,
            vision_module=vision_module,
            strategy_module=strategy_module,
            config=config,
        )

    def _parse_manifest(self, path: Path) -> PluginManifest:
        """Parse a ``manifest.yaml`` file.

        Args:
            path: Path to the manifest file.

        Returns:
            Parsed ``PluginManifest``.

        Raises:
            PluginLoaderError: If the file cannot be read or is missing
                required fields.

        """
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw: dict[str, Any] | None = yaml.safe_load(fh)
            if raw is None:
                raise PluginLoaderError(f"Empty manifest: {path}")
            name = str(raw.get("name", "") or "")
            version = str(raw.get("version", "") or "")
            if not name:
                raise PluginLoaderError(f"Plugin manifest {path} is missing required field 'name'")
            if not version:
                raise PluginLoaderError(
                    f"Plugin manifest {path} is missing required field 'version'"
                )
            return PluginManifest(name=name, version=version)
        except (OSError, yaml.YAMLError) as exc:
            raise PluginLoaderError(f"Failed to read manifest {path}: {exc}") from exc

    def _load_config(self, path: Path) -> dict[str, Any]:
        """Load optional ``config.yaml`` for a plugin.

        Args:
            path: Path to the config file.

        Returns:
            Parsed dictionary, or an empty dict if the file does not
            exist.

        """
        if not path.is_file():
            return {}
        try:
            with path.open("r", encoding="utf-8") as fh:
                raw: dict[str, Any] | None = yaml.safe_load(fh)
            return raw if raw is not None else {}
        except (OSError, yaml.YAMLError):
            self._logger.warning("plugin_loader.config_parse_failed", path=str(path))
            return {}

    def _import_module(self, plugin_dir: Path, name: str) -> ModuleType | None:
        """Import a Python module from a plugin directory.

        Args:
            plugin_dir: Plugin directory path.
            name: Module filename without extension (e.g. ``"bot"``).

        Returns:
            The imported module, or ``None`` if the file does not exist.

        """
        file_path = plugin_dir / f"{name}.py"
        if not file_path.is_file():
            return None

        module_name = f"ugaf_plugin_{plugin_dir.name}_{name}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            self._logger.warning(
                "plugin_loader.import_failed",
                path=str(file_path),
            )
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            self._logger.error(
                "plugin_loader.import_error",
                path=str(file_path),
                error=str(exc),
            )
            return None

        return module
