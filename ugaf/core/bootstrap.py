"""Application bootstrap: wires together core services."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from ugaf.core.config import Config
from ugaf.core.context import AppContext
from ugaf.core.di import DependencyContainer
from ugaf.core.event_bus import Event, EventBus
from ugaf.core.exceptions import ApplicationError
from ugaf.core.health import HealthRegistry, HealthResult, HealthStatus
from ugaf.core.logger import Logger, configure_logger, get_logger
from ugaf.core.platform import detect_platform

# Imported only for type checking; the real imports happen lazily
# inside initialize() to avoid a runtime circular import (see the
# comment in ugaf/core/context.py for the full cycle).
if TYPE_CHECKING:
    from ugaf.device.manager import DeviceManager
    from ugaf.plugins.manager import PluginManager

__all__ = [
    "Application",
]

_DEFAULT_CONFIG_PATH = Path("config/default.yaml")
_DEFAULT_GAMES_DIR = Path("games")


class Application:
    """Top-level application container.

    Wires together ``Config``, ``Logger``, ``EventBus``,
    ``PluginManager``, and ``DeviceManager``, then manages the
    lifecycle.

    Usage::

        app = Application()
        await app.initialize()
        await app.start()
        # ...
        await app.stop()
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        games_dir: Path | str | None = None,
    ) -> None:
        """Initialise the application.

        Args:
            config_path: Path to the main YAML configuration file.
                Defaults to ``config/default.yaml``.
            games_dir: Path to the games plugin directory. Defaults to
                ``games``.

        """
        self._config_path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._games_dir = Path(games_dir) if games_dir else _DEFAULT_GAMES_DIR

        self.config: Config | None = None
        self.logger: Logger | None = None
        self.event_bus: EventBus | None = None
        self.plugin_manager: PluginManager | None = None
        self.device_manager: DeviceManager | None = None
        self._container = DependencyContainer()
        self._health_registry: HealthRegistry | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Load config, configure logging, create core services.

        This method does **not** start plugins or the event loop.

        Raises:
            ApplicationError: If already initialized.

        """
        if self.config is not None:
            raise ApplicationError("Application is already initialized")

        # Local imports: see the TYPE_CHECKING comment above for why
        # these cannot be module-level imports.
        from ugaf.device.adb_provider import AdbDeviceProvider
        from ugaf.device.manager import DeviceManager
        from ugaf.plugins.manager import PluginManager

        self.config = Config(self._config_path)
        logger = configure_logger(self.config)
        self.logger = logger
        self.event_bus = EventBus(logger=logger)

        self.device_manager = DeviceManager(event_bus=self.event_bus, logger=logger)
        adb_executable = str(self.config.get("device.adb.executable", "adb"))
        self.device_manager.register_provider("adb", AdbDeviceProvider(executable=adb_executable))

        self.plugin_manager = PluginManager(
            config=self.config,
            logger=logger,
            event_bus=self.event_bus,
            games_dir=self._games_dir,
            device_manager=self.device_manager,
        )

        self._health_registry = HealthRegistry()
        self._health_registry.register("config", self._check_config_health)
        self._health_registry.register("event_bus", self._check_event_bus_health)
        self._health_registry.register("plugin_manager", self._check_plugin_manager_health)
        self._health_registry.register("device_manager", self._check_device_manager_health)

        logger.info("app.initialized", config_path=str(self._config_path))

    async def start(self, auto_start_plugins: bool = True) -> None:
        """Start the application.

        Discovers plugins, starts them, and publishes ``app.started``.

        Args:
            auto_start_plugins: If ``True`` (the default, matching the
                CLI's ``ugaf start`` — a headless automation runner),
                every discovered plugin is immediately initialized and
                started. If ``False`` (used by the web control panel,
                where the user starts plugins explicitly from the UI),
                plugins are only discovered/registered here; a caller
                must call ``plugin_manager.initialize()``/``start()``
                per plugin itself.

        Raises:
            RuntimeError: If not initialized.

        """
        event_bus = self.event_bus
        if event_bus is None:
            raise ApplicationError("Call initialize() before start()")
        logger = get_logger()

        self._running = True
        logger.info("app.starting")

        await event_bus.publish(
            Event(topic="app.starting", data={"config_path": str(self._config_path)})
        )

        if self.plugin_manager is not None:
            self.plugin_manager.discover()
            if auto_start_plugins:
                await self.plugin_manager.initialize_all()
                await self.plugin_manager.start_all()

        if self.device_manager is not None:
            self.device_manager.discover()
            if self.config is not None and bool(self.config.get("device.monitor.enabled", False)):
                interval = float(self.config.get("device.monitor.interval", 5.0))
                await self.device_manager.start_monitoring(interval=interval)

        await event_bus.publish(
            Event(topic="app.started", data={"config_path": str(self._config_path)})
        )
        logger.info("app.started")

    async def stop(self) -> None:
        """Gracefully stop the application.

        Stops plugins and publishes ``app.stopped``.

        Raises:
            RuntimeError: If not initialized.

        """
        event_bus = self.event_bus
        if event_bus is None:
            raise ApplicationError("Application is not initialized")
        logger = get_logger()

        self._running = False
        logger.info("app.stopping")

        await event_bus.publish(Event(topic="app.stopping"))

        if self.plugin_manager is not None:
            await self.plugin_manager.stop_all()
            await self.plugin_manager.shutdown_all()

        if self.device_manager is not None:
            await self.device_manager.stop_monitoring()

        await event_bus.publish(Event(topic="app.stopped"))
        logger.info("app.stopped")

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    async def run_forever(self) -> None:
        """Initialize, start, and wait for a shutdown signal.

        Registers signal handlers for ``SIGINT`` and ``SIGTERM`` so
        that the application shuts down on Ctrl+C.
        """
        await self.initialize()
        await self.start()

        loop = asyncio.get_event_loop()
        stop_event = asyncio.Event()
        logger = get_logger()

        def _signal_handler(sig: int, _frame: FrameType | None) -> None:
            try:
                sig_name = signal.Signals(sig).name
            except ValueError:
                sig_name = str(sig)
            logger.info("app.signal_received", signal=sig_name)
            stop_event.set()

        try:
            loop.add_signal_handler(signal.SIGINT, _signal_handler, signal.SIGINT, None)
            loop.add_signal_handler(signal.SIGTERM, _signal_handler, signal.SIGTERM, None)
        except (NotImplementedError, AttributeError):
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, _signal_handler, sig, None)
                except (NotImplementedError, AttributeError):
                    pass

        await stop_event.wait()
        await self.stop()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    async def health(self) -> list[HealthResult]:
        """Run all registered health checks.

        Returns:
            List of ``HealthResult`` for every registered check.

        Raises:
            ApplicationError: If not initialized.

        """
        if self._health_registry is None:
            raise ApplicationError("Application is not initialized")
        return await self._health_registry.run_all()

    @property
    def context(self) -> AppContext:
        """Return the application context (available after initialisation).

        Raises:
            ApplicationError: If accessed before ``initialize()``.

        """
        if self.config is None:
            raise ApplicationError("Application is not initialized")
        logger = self.logger
        event_bus = self.event_bus
        plugin_manager = self.plugin_manager
        device_manager = self.device_manager
        health_registry = self._health_registry
        assert logger is not None
        assert event_bus is not None
        assert plugin_manager is not None
        assert device_manager is not None
        assert health_registry is not None
        return AppContext(
            config=self.config,
            logger=logger,
            event_bus=event_bus,
            container=self._container,
            plugin_manager=plugin_manager,
            device_manager=device_manager,
            health_registry=health_registry,
            platform=detect_platform(),
        )

    @property
    def is_running(self) -> bool:
        """Return whether the application is running."""
        return self._running

    # ------------------------------------------------------------------
    # Internal health checks
    # ------------------------------------------------------------------

    async def _check_config_health(self) -> HealthResult:
        """Verify that the configuration is loaded."""
        if self.config is None:
            return HealthResult(
                status=HealthStatus.ERROR,
                component="config",
                message="Config not loaded",
            )
        return HealthResult(
            status=HealthStatus.HEALTHY,
            component="config",
            message="Config loaded",
        )

    async def _check_event_bus_health(self) -> HealthResult:
        """Verify that the event bus is available."""
        if self.event_bus is None:
            return HealthResult(
                status=HealthStatus.ERROR,
                component="event_bus",
                message="Event bus not available",
            )
        return HealthResult(
            status=HealthStatus.HEALTHY,
            component="event_bus",
            message="Event bus operational",
        )

    async def _check_plugin_manager_health(self) -> HealthResult:
        """Verify that the plugin manager is available."""
        if self.plugin_manager is None:
            return HealthResult(
                status=HealthStatus.ERROR,
                component="plugin_manager",
                message="Plugin manager not available",
            )
        registered = len(self.plugin_manager.registry.list())
        return HealthResult(
            status=HealthStatus.HEALTHY,
            component="plugin_manager",
            message=f"{registered} plugin(s) registered",
        )

    async def _check_device_manager_health(self) -> HealthResult:
        """Verify that the device manager is available."""
        if self.device_manager is None:
            return HealthResult(
                status=HealthStatus.ERROR,
                component="device_manager",
                message="Device manager not available",
            )
        known = len(self.device_manager.list_devices())
        return HealthResult(
            status=HealthStatus.HEALTHY,
            component="device_manager",
            message=f"{known} device(s) known",
        )
