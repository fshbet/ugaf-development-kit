"""Plugin lifecycle manager.

Orchestrates discovery, loading, and lifecycle of UGAF game plugins.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from ugaf.apps.manager import ApplicationManager
from ugaf.core.config import Config
from ugaf.core.di import DependencyContainer
from ugaf.core.event_bus import Event, EventBus
from ugaf.core.logger import Logger, get_logger
from ugaf.device.manager import DeviceManager
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


def _instance_key(plugin_id: str, device_id: str | None) -> str:
    """Return the lifecycle dict key for a plugin instance.

    A plain ``plugin_id`` when *device_id* is ``None`` (the original,
    single-instance-per-plugin behaviour every existing caller relies
    on), or a composite ``"{plugin_id}@{device_id}"`` key when a
    specific device is given — this is what lets the *same* automation
    run as several independent, concurrent instances, one per target
    device (see :class:`PluginManager`'s class docstring).
    """
    return plugin_id if device_id is None else f"{plugin_id}@{device_id}"


class PluginManager:
    """Orchestrates plugin discovery, loading, and lifecycle.

    Every lifecycle method (``initialize``/``start``/``pause``/
    ``resume``/``stop``/``shutdown``/``health``) accepts an optional
    ``device_id``. Omitting it (the default) preserves the original
    behaviour: one lifecycle instance per plugin, shared across
    however it's invoked. Passing a ``device_id`` creates (or reuses)
    a *separate* instance of that same plugin class bound to that
    device — so ``games/shadow_fight_3`` can run concurrently against
    two different phones, each with its own state, its own
    :class:`~ugaf.sdk.state.GameState`, and its own logs, with a crash
    in one instance never touching the other. This is deliberately not
    a new subsystem: it is the same :class:`PluginLifecycle`,
    ``GamePlugin`` instance, and instance dict this class already had —
    only the dict key gained an optional device suffix.

    Usage::

        manager = PluginManager(
            config=config,
            logger=logger,
            event_bus=event_bus,
            games_dir=Path("games"),
        )
        manager.discover()

        # Single-instance (unchanged):
        await manager.initialize_all()
        await manager.start_all()

        # Multi-device — two independent instances of the same plugin:
        await manager.initialize("shadow_fight_3", device_id="deviceA")
        await manager.initialize("shadow_fight_3", device_id="deviceB")
        await manager.start("shadow_fight_3", device_id="deviceA")
        await manager.start("shadow_fight_3", device_id="deviceB")

    """

    def __init__(
        self,
        config: Config,
        logger: Logger | None = None,
        event_bus: EventBus | None = None,
        games_dir: Path | str | None = None,
        registry: PluginRegistry | None = None,
        loader: PluginLoader | None = None,
        device_manager: DeviceManager | None = None,
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
            device_manager: Optional :class:`~ugaf.device.manager.DeviceManager`.
                When provided, it is registered as a DI singleton in
                every plugin's :class:`~ugaf.sdk.context.GameContext`,
                so a plugin can resolve it and build its own
                per-device ``InputManager`` instances — this is the
                intended extension point for plugins that drive
                multiple simultaneous Android devices, rather than
                ``PluginManager`` prescribing a single global input
                target.

        """
        self._config = config
        self._logger = logger or get_logger()
        self._event_bus = event_bus
        self._games_dir = Path(games_dir) if games_dir else Path("games")
        self._registry = registry or PluginRegistry()
        self._loader = loader or PluginLoader(self._games_dir, logger=self._logger)
        self._device_manager = device_manager
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
        """Return all managed lifecycle wrappers, keyed by instance key.

        The key is the plain plugin ID for a single (device_id-less)
        instance, or ``"{plugin_id}@{device_id}"`` for a
        device-bound instance — see :func:`_instance_key`.
        """
        return dict(self._lifecycles)

    @property
    def context(self) -> GameContext | None:
        """Return the shared game context, if created.

        Device-bound instances (created with a ``device_id``) get
        their own :class:`~ugaf.sdk.context.GameContext` copy with
        ``device_id`` set — see :meth:`_get_or_create_context` — but
        share this same underlying service container.
        """
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

    def load(self, plugin_id: str, device_id: str | None = None) -> PluginLifecycle:
        """Load and create a lifecycle wrapper for a registered plugin.

        Args:
            plugin_id: The plugin identifier.
            device_id: If given, creates/reuses a distinct instance of
                this plugin bound to this device (see the class
                docstring); if omitted, reuses the single shared
                instance as before.

        Returns:
            The :class:`PluginLifecycle` wrapper.

        Raises:
            KeyError: If the plugin is not registered.

        """
        key = _instance_key(plugin_id, device_id)
        if key in self._lifecycles:
            return self._lifecycles[key]

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
        self._lifecycles[key] = lifecycle
        return lifecycle

    # ------------------------------------------------------------------
    # Lifecycle: individual plugin
    # ------------------------------------------------------------------

    async def initialize(
        self,
        plugin_id: str,
        context: GameContext | None = None,
        device_id: str | None = None,
    ) -> None:
        """Initialize a single plugin (or a specific device-bound instance of it).

        Args:
            plugin_id: The plugin identifier.
            context: Optional game context.  Uses the manager's context
                if not provided.
            device_id: See :meth:`load`.

        """
        ctx = context or self._get_or_create_context(device_id=device_id)
        lifecycle = self.load(plugin_id, device_id=device_id)
        await lifecycle.initialize(ctx)

    async def start(self, plugin_id: str, device_id: str | None = None) -> None:
        """Start a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        await lifecycle.start()

    async def pause(self, plugin_id: str, device_id: str | None = None) -> None:
        """Pause a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        await lifecycle.pause()

    async def resume(self, plugin_id: str, device_id: str | None = None) -> None:
        """Resume a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        await lifecycle.resume()

    async def stop(self, plugin_id: str, device_id: str | None = None) -> None:
        """Stop a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        await lifecycle.stop()

    async def shutdown(self, plugin_id: str, device_id: str | None = None) -> None:
        """Shut down a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        await lifecycle.shutdown()

    async def health(self, plugin_id: str, device_id: str | None = None) -> dict[str, Any]:
        """Return health for a single plugin (or a specific device-bound instance of it)."""
        lifecycle = self._get_lifecycle(plugin_id, device_id=device_id)
        return await lifecycle.health()

    # ------------------------------------------------------------------
    # Lifecycle: all plugins
    # ------------------------------------------------------------------

    async def initialize_all(self) -> None:
        """Initialize all registered plugins.

        One plugin's failure (e.g. a game plugin that requires
        hardware not currently connected) does not prevent the others
        from starting — each is initialized independently, with
        failures logged rather than raised. Use
        :meth:`~PluginManager.health` per plugin to check whether it
        ended up in ``GameState.ERROR``.
        """
        ctx = self._get_or_create_context()
        for meta in sorted(self._registry.list(), key=lambda m: m.id):
            try:
                await self.initialize(meta.id, context=ctx)
            except Exception as exc:
                self._logger.warning(
                    "plugin_manager.initialize_all_failed", plugin_id=meta.id, error=str(exc)
                )

    async def start_all(self) -> None:
        """Start all initialized plugins.

        Fault-isolated per plugin, mirroring :meth:`initialize_all` —
        see its docstring for why.
        """
        for key in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[key]
            if lifecycle.state is GameState.INITIALIZED:
                try:
                    await lifecycle.start()
                except Exception as exc:
                    self._logger.warning(
                        "plugin_manager.start_all_failed", plugin_id=key, error=str(exc)
                    )

    async def pause_all(self) -> None:
        """Pause all running plugins."""
        for key in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[key]
            if lifecycle.state is GameState.RUNNING:
                await lifecycle.pause()

    async def resume_all(self) -> None:
        """Resume all paused plugins."""
        for key in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[key]
            if lifecycle.state is GameState.PAUSED:
                await lifecycle.resume()

    async def stop_all(self) -> None:
        """Stop all running or paused plugins.

        Fault-isolated per instance: one device-bound instance failing
        to stop cleanly does not block the others from stopping.
        """
        for key in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[key]
            if lifecycle.state in (GameState.RUNNING, GameState.PAUSED):
                try:
                    await lifecycle.stop()
                except Exception as exc:
                    self._logger.warning(
                        "plugin_manager.stop_all_failed", plugin_id=key, error=str(exc)
                    )

    async def shutdown_all(self) -> None:
        """Shut down all plugins."""
        for key in self._sorted_lifecycle_ids():
            lifecycle = self._lifecycles[key]
            if lifecycle.state is not GameState.SHUTDOWN:
                await lifecycle.shutdown()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_lifecycle(self, plugin_id: str, device_id: str | None = None) -> PluginLifecycle:
        """Return a lifecycle wrapper, loading it if necessary."""
        key = _instance_key(plugin_id, device_id)
        if key not in self._lifecycles:
            return self.load(plugin_id, device_id=device_id)
        return self._lifecycles[key]

    def _sorted_lifecycle_ids(self) -> list[str]:
        """Return lifecycle instance keys sorted by plugin priority then name."""

        def _sort_key(key: str) -> tuple[int, str]:
            lc = self._lifecycles[key]
            return (lc.metadata.priority, lc.metadata.name)

        return sorted(self._lifecycles, key=_sort_key)

    def _get_or_create_context(self, device_id: str | None = None) -> GameContext:
        """Return the shared game context, or a per-device variant of it.

        The underlying services (config, logger, event bus, DI
        container) are created once and shared by every plugin
        instance — only ``device_id`` varies between instances, via a
        cheap :func:`dataclasses.replace` copy, so a device-bound
        instance can tell which device it targets without needing its
        own separate service wiring.
        """
        if self._context is None:
            container = DependencyContainer()
            self._register_vision_services(container)
            if self._device_manager is not None:
                container.register_singleton(DeviceManager, self._device_manager)
                app_manager = ApplicationManager(self._device_manager, logger=self._logger)
                container.register_singleton(ApplicationManager, app_manager)

            self._context = GameContext(
                config=self._config,
                logger=self._logger,
                event_bus=self._event_bus or EventBus(logger=self._logger),
                service_container=container,
            )
        if device_id is None:
            return self._context
        return dataclasses.replace(self._context, device_id=device_id)

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

        screenshot_manager = None
        try:
            from ugaf.vision.screenshot_manager import ScreenshotManager

            screenshot_manager = ScreenshotManager(config=self._config, imaging=imaging)
            screenshot_manager.connect()
        except Exception as exc:
            self._logger.warning("plugin_manager.screenshot_unavailable", error=str(exc))
            screenshot_manager = None

        try:
            from ugaf.vision.manager import VisionManager

            vision = VisionManager(
                imaging=imaging,
                screenshot_provider=screenshot_manager,
                config=self._config,
            )
        except Exception:
            self._logger.warning("plugin_manager.vision_unavailable")
            return

        container.register_singleton(ImagingManager, imaging)
        if screenshot_manager is not None:
            from ugaf.vision.screenshot_manager import ScreenshotManager

            container.register_singleton(ScreenshotManager, screenshot_manager)
        container.register_singleton(VisionManager, vision)
