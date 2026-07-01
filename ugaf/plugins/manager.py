"""Plugin lifecycle manager.

Orchestrates discovery, loading, and lifecycle of UGAF game plugins.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ugaf.core.config import Config
from ugaf.core.di import DependencyContainer
from ugaf.core.event_bus import Event, EventBus
from ugaf.core.logger import Logger, get_logger
from ugaf.plugins.lifecycle import PluginLifecycle
from ugaf.plugins.loader import PluginLoader
from ugaf.plugins.registry import PluginRegistry
from ugaf.sdk.context import GameContext
from ugaf.sdk.events import PLUGIN_LOADED
from ugaf.sdk.exceptions import GameSDKError
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState

__all__ = [
    "PluginManager",
]


class PluginManager:
    """Orchestrates plugin discovery, loading, and lifecycle.

    Usage::

        manager = PluginManager(
            config=config,
            logger=logger,
            event_bus=event_bus,
            games_dir=Path("games"),
        )
        manager.discover()
        await manager.initialize_all()
        await manager.start_all()
        # ...
        await manager.stop_all()
        await manager.shutdown_all()

    """

    def __init__(
        self,
        config: Config,
        logger: Logger | None = None,
        event_bus: EventBus | None = None,
        games_dir: Path | str | None = None,
        registry: PluginRegistry | None = None,
        loader: PluginLoader | None = None,
    ) -> None:
        """Initialise the plugin manager.

        Args:
            config: Application configuration.
            logger: Optional logger.
            event_bus: Optional event bus.
            games_dir: Path to the games plugin directory.
                Defaults to ``games``.
            registry: Optional plugin registry.  Creates one if not
                provided.
            loader: Optional plugin loader.  Creates one if not
                provided.

        """
        self._config = config
        self._logger = logger or get_logger()
        self._event_bus = event_bus
        self._games_dir = Path(games_dir) if games_dir else Path("games")
        self._registry = registry or PluginRegistry()
        self._loader = loader or PluginLoader(self._games_dir, logger=self._logger)
        self._lifecycles: dict[str, PluginLifecycle] = {}
        self._context: GameContext | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def registry(self) -> PluginRegistry:
        """Return the plugin registry."""
        return self._registry

    @property
    def lifecycles(self) -> dict[str, PluginLifecycle]:
        """Return all managed lifecycle wrappers keyed by plugin ID."""
        return dict(self._lifecycles)

    @property
    def context(self) -> GameContext | None:
        """Return the game context, if created."""
        return self._context

    # ------------------------------------------------------------------
    # Discovery & loading
    # ------------------------------------------------------------------

    def discover(self) -> list[PluginMetadata]:
        """Scan the games directory and register all valid plugins.

        Returns:
            List of metadata for newly discovered plugins.

        """
        discovered: list[PluginMetadata] = []
        for metadata, plugin_cls in self._loader.discover():
            try:
                self._registry.register(metadata, plugin_cls)
                discovered.append(metadata)
                self._logger.info(
                    "plugin_manager.registered",
                    name=metadata.name,
                    id=metadata.id,
                )
            except GameSDKError:
                self._logger.warning(
                    "plugin_manager.duplicate_skipped",
                    name=metadata.name,
                    id=metadata.id,
                )

        if self._event_bus is not None:
            for metadata in discovered:
                import asyncio

                try:
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(
                            self._event_bus.publish(
                                Event(
                                    topic=PLUGIN_LOADED,
                                    data={
                                        "plugin_id": metadata.id,
                                        "name": metadata.name,
                                        "version": metadata.version,
                                    },
                                )
                            )
                        )
                except RuntimeError:
                    pass

        return discovered

    def load(self, plugin_id: str) -> PluginLifecycle:
        """Load and create a lifecycle wrapper for a registered plugin.

        Args:
            plugin_id: The plugin identifier.

        Returns:
            The :class:`PluginLifecycle` wrapper.

        Raises:
            KeyError: If the plugin is not registered.

        """
        if plugin_id in self._lifecycles:
            return self._lifecycles[plugin_id]

        plugin_cls = self._registry.find(plugin_id)
        if plugin_cls is None:
            raise KeyError(f"Plugin {plugin_id!r} is not registered")

        metadata = self._registry.get_metadata(plugin_id)
        if metadata is None:
            raise KeyError(f"Plugin {plugin_id!r} has no metadata")
        event_bus = self._event_bus or EventBus(logger=self._logger)
        plugin = plugin_cls()
        lifecycle = PluginLifecycle(
            plugin=plugin,
            metadata=metadata,
            event_bus=event_bus,
            logger=self._logger,
        )
        self._lifecycles[plugin_id] = lifecycle
        return lifecycle

    # ------------------------------------------------------------------
    # Lifecycle: individual plugin
    # ------------------------------------------------------------------

    async def initialize(self, plugin_id: str, context: GameContext | None = None) -> None:
        """Initialize a single plugin.

        Args:
            plugin_id: The plugin identifier.
            context: Optional game context.  Uses the manager's context
                if not provided.

        """
        ctx = context or self._get_or_create_context()
        lifecycle = self.load(plugin_id)
        await lifecycle.initialize(ctx)

    async def start(self, plugin_id: str) -> None:
        """Start a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        await lifecycle.start()

    async def pause(self, plugin_id: str) -> None:
        """Pause a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        await lifecycle.pause()

    async def resume(self, plugin_id: str) -> None:
        """Resume a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        await lifecycle.resume()

    async def stop(self, plugin_id: str) -> None:
        """Stop a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        await lifecycle.stop()

    async def shutdown(self, plugin_id: str) -> None:
        """Shut down a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        await lifecycle.shutdown()

    async def health(self, plugin_id: str) -> dict[str, Any]:
        """Return health for a single plugin."""
        lifecycle = self._get_lifecycle(plugin_id)
        return await lifecycle.health()

    # ------------------------------------------------------------------
    # Lifecycle: all plugins
    # ------------------------------------------------------------------

    async def initialize_all(self) -> None:
        """Initialize all registered plugins."""
        ctx = self._get_or_create_context()
        for meta in sorted(self._registry.list(), key=lambda m: m.id):
            await self.initialize(meta.id, context=ctx)

    async def start_all(self) -> None:
        """Start all initialized plugins."""
        for plugin_id in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[plugin_id]
            if lifecycle.state is GameState.INITIALIZED:
                await lifecycle.start()

    async def pause_all(self) -> None:
        """Pause all running plugins."""
        for plugin_id in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[plugin_id]
            if lifecycle.state is GameState.RUNNING:
                await lifecycle.pause()

    async def resume_all(self) -> None:
        """Resume all paused plugins."""
        for plugin_id in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[plugin_id]
            if lifecycle.state is GameState.PAUSED:
                await lifecycle.resume()

    async def stop_all(self) -> None:
        """Stop all running or paused plugins."""
        for plugin_id in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[plugin_id]
            if lifecycle.state in (GameState.RUNNING, GameState.PAUSED):
                await lifecycle.stop()

    async def shutdown_all(self) -> None:
        """Shut down all plugins."""
        for plugin_id in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[plugin_id]
            if lifecycle.state is not GameState.SHUTDOWN:
                await lifecycle.shutdown()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lifecycle(self, plugin_id: str) -> PluginLifecycle:
        """Return a lifecycle wrapper, loading it if necessary."""
        if plugin_id not in self._lifecycles:
            return self.load(plugin_id)
        return self._lifecycles[plugin_id]

    def _sorted_lifecycle_ids(self) -> list[str]:
        """Return lifecycle IDs sorted by plugin priority then name."""

        def _sort_key(pid: str) -> tuple[int, str]:
            lc = self._lifecycles[pid]
            return (lc.metadata.priority, lc.metadata.name)

        return sorted(self._lifecycles, key=_sort_key)

    def _get_or_create_context(self) -> GameContext:
        """Create the game context if it does not exist yet."""
        if self._context is None:
            container = DependencyContainer()
            self._register_vision_services(container)

            self._context = GameContext(
                config=self._config,
                logger=self._logger,
                event_bus=self._event_bus or EventBus(logger=self._logger),
                service_container=container,
            )
        return self._context

    def _register_vision_services(self, container: DependencyContainer) -> None:
        """Register imaging and vision services in the DI container.

        If OpenCV is not available the services are skipped with a
        warning rather than failing.
        """
        try:
            from ugaf.imaging.manager import ImagingManager

            imaging = ImagingManager(config=self._config)
        except Exception:
            self._logger.warning("plugin_manager.imaging_unavailable")
            return

        try:
            from ugaf.vision.manager import VisionManager

            vision = VisionManager(imaging=imaging, config=self._config)
        except Exception:
            self._logger.warning("plugin_manager.vision_unavailable")
            return

        container.register_singleton(ImagingManager, imaging)
        container.register_singleton(VisionManager, vision)
