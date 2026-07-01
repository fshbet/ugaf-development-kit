"""Thread-safe registry for UGAF game plugin classes.

This registry maps plugin IDs to their corresponding
:class:`~ugaf.sdk.game.GamePlugin` subclasses and metadata.  No
hardcoded plugin references exist in this module.

"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from ugaf.sdk.capabilities import Capability
from ugaf.sdk.exceptions import PluginValidationError
from ugaf.sdk.metadata import PluginMetadata

if TYPE_CHECKING:
    from ugaf.sdk.game import GamePlugin

__all__ = [
    "PluginRegistry",
]


class PluginRegistry:
    """Thread-safe registry for game plugin classes.

    Usage::

        registry = PluginRegistry()
        registry.register(metadata, MyPlugin)
        found = registry.find("my_game")
        for meta, cls in registry.find_by_capability(Capability.INPUT):
            ...

    """

    def __init__(self) -> None:
        """Initialize an empty plugin registry."""
        self._lock = threading.Lock()
        self._plugins: dict[str, type[GamePlugin]] = {}
        self._metadata: dict[str, PluginMetadata] = {}

    def register(
        self,
        metadata: PluginMetadata,
        plugin_cls: type[GamePlugin],
    ) -> None:
        """Register a plugin class under its metadata.

        Args:
            metadata: The plugin's metadata descriptor.
            plugin_cls: The concrete :class:`GamePlugin` subclass.

        Raises:
            PluginValidationError: If a plugin with the same ID or
                name is already registered.

        """
        with self._lock:
            if metadata.id in self._plugins:
                raise PluginValidationError(f"Plugin with id {metadata.id!r} is already registered")
            for existing in self._metadata.values():
                if existing.name == metadata.name:
                    raise PluginValidationError(
                        f"Plugin with name {metadata.name!r} is already registered"
                    )
            self._plugins[metadata.id] = plugin_cls
            self._metadata[metadata.id] = metadata

    def unregister(self, plugin_id: str) -> None:
        """Remove a registered plugin.

        Args:
            plugin_id: The plugin identifier.

        Raises:
            KeyError: If *plugin_id* is not registered.

        """
        with self._lock:
            self._plugins.pop(plugin_id)
            self._metadata.pop(plugin_id)

    def find(self, plugin_id: str) -> type[GamePlugin] | None:
        """Look up a plugin class by its identifier.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            The plugin class, or ``None`` if not found.

        """
        return self._plugins.get(plugin_id)

    def get_metadata(self, plugin_id: str) -> PluginMetadata | None:
        """Look up plugin metadata by its identifier.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            The metadata, or ``None`` if not found.

        """
        return self._metadata.get(plugin_id)

    def find_by_capability(
        self,
        capability: Capability,
    ) -> list[tuple[PluginMetadata, type[GamePlugin]]]:
        """Return all plugins that declare a given capability.

        Args:
            capability: The capability to filter by.

        Returns:
            List of ``(metadata, plugin_class)`` tuples.

        """
        results: list[tuple[PluginMetadata, type[GamePlugin]]] = []
        with self._lock:
            for pid, meta in self._metadata.items():
                if capability in meta.capabilities:
                    results.append((meta, self._plugins[pid]))
        return results

    def list(self) -> list[PluginMetadata]:
        """Return all registered plugin metadata, sorted by priority then name.

        Returns:
            Sorted list of :class:`PluginMetadata`.

        """
        with self._lock:
            return sorted(
                self._metadata.values(),
                key=lambda m: (m.priority, m.name),
            )

    @property
    def count(self) -> int:
        """Return the number of registered plugins."""
        return len(self._plugins)
