"""Filesystem discovery and dynamic import of UGAF game plugins."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

from ugaf.core.logger import Logger, get_logger
from ugaf.plugins.validator import PluginValidator
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata

__all__ = [
    "PluginLoader",
]


class PluginLoader:
    """Discovers game plugins from a directory and imports them.

    Each plugin must be in a subdirectory containing:
    - ``manifest.yaml`` — plugin descriptor
    - ``plugin.py`` — module with a :class:`GamePlugin` subclass

    Usage::

        loader = PluginLoader(Path("games"))
        for metadata, cls in loader.discover():
            registry.register(metadata, cls)

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

    def discover(self) -> list[tuple[PluginMetadata, type[GamePlugin]]]:
        """Scan the games directory and load every valid plugin.

        Returns:
            List of ``(metadata, plugin_class)`` tuples for each
            successfully loaded plugin.

        """
        if not self._games_dir.is_dir():
            self._logger.warning(
                "plugin_loader.games_dir_not_found",
                path=str(self._games_dir),
            )
            return []

        discovered: list[tuple[PluginMetadata, type[GamePlugin]]] = []

        for entry in sorted(self._games_dir.iterdir()):
            if not entry.is_dir():
                continue

            manifest_path = entry / "manifest.yaml"
            plugin_path = entry / "plugin.py"

            if not manifest_path.is_file():
                self._logger.debug(
                    "plugin_loader.skipped_no_manifest",
                    directory=str(entry),
                )
                continue

            if not plugin_path.is_file():
                self._logger.debug(
                    "plugin_loader.skipped_no_plugin",
                    directory=str(entry),
                )
                continue

            try:
                metadata, plugin_cls = self._load_plugin(entry)
                discovered.append((metadata, plugin_cls))
                self._logger.info(
                    "plugin_loader.discovered",
                    name=metadata.name,
                    id=metadata.id,
                    version=metadata.version,
                )
            except Exception as exc:
                self._logger.warning(
                    "plugin_loader.load_failed",
                    directory=str(entry),
                    error=str(exc),
                )

        return discovered

    def _load_plugin(
        self,
        plugin_dir: Path,
    ) -> tuple[PluginMetadata, type[GamePlugin]]:
        """Load a single plugin from its directory.

        Args:
            plugin_dir: The plugin's directory.

        Returns:
            A ``(metadata, plugin_class)`` tuple.

        Raises:
            PluginValidationError: If the manifest is invalid.

        """
        manifest_path = plugin_dir / "manifest.yaml"
        plugin_path = plugin_dir / "plugin.py"

        with manifest_path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] | None = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            from ugaf.sdk.exceptions import PluginValidationError

            raise PluginValidationError(f"Invalid manifest in {manifest_path}: expected a mapping")

        metadata = PluginValidator.validate_manifest(raw)
        plugin_cls = self._import_plugin_class(plugin_path, metadata)

        return metadata, plugin_cls

    def _import_plugin_class(
        self,
        plugin_path: Path,
        metadata: PluginMetadata,
    ) -> type[GamePlugin]:
        """Import a ``plugin.py`` module and extract the ``GamePlugin`` subclass.

        Args:
            plugin_path: Path to ``plugin.py``.
            metadata: The plugin's metadata (used for naming).

        Returns:
            The :class:`GamePlugin` subclass found in the module.

        Raises:
            PluginValidationError: If no ``GamePlugin`` subclass is
                found.

        """
        module_name = f"ugaf_game_{metadata.id}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec is None or spec.loader is None:
            from ugaf.sdk.exceptions import PluginValidationError

            raise PluginValidationError(f"Failed to create module spec for {plugin_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        plugin_cls = self._find_game_plugin_class(module)
        if plugin_cls is None:
            from ugaf.sdk.exceptions import PluginValidationError

            raise PluginValidationError(f"No GamePlugin subclass found in {plugin_path}")

        return plugin_cls

    @staticmethod
    def _find_game_plugin_class(module: object) -> type[GamePlugin] | None:
        """Find the first ``GamePlugin`` subclass in a module.

        Args:
            module: The imported module.

        Returns:
            The first :class:`GamePlugin` subclass, or ``None``.

        """
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, GamePlugin) and obj is not GamePlugin:
                return obj
        return None
