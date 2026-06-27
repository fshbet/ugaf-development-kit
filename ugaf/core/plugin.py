"""Plugin lifecycle management for the UGAF framework."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ugaf.core.event_bus import Event, EventBus
from ugaf.core.exceptions import PluginLifecycleError
from ugaf.core.logger import Logger, get_logger
from ugaf.core.plugin_loader import PluginInfo

__all__ = [
    "PluginInstance",
    "PluginState",
]


class PluginState(Enum):
    """Lifecycle state of a plugin instance.

    Attributes:
        CREATED: Plugin discovered but not initialized.
        INITIALIZED: Plugin has been initialized.
        STARTED: Plugin is actively running.
        PAUSED: Plugin has been paused.
        STOPPED: Plugin has been stopped.
        SHUTDOWN: Plugin has been shut down (terminal).

    """

    CREATED = "created"
    INITIALIZED = "initialized"
    STARTED = "started"
    PAUSED = "paused"
    STOPPED = "stopped"
    SHUTDOWN = "shutdown"


# Valid state transitions
_TRANSITIONS: dict[PluginState, set[PluginState]] = {
    PluginState.CREATED: {PluginState.INITIALIZED},
    PluginState.INITIALIZED: {PluginState.STARTED, PluginState.SHUTDOWN},
    PluginState.STARTED: {PluginState.PAUSED, PluginState.STOPPED},
    PluginState.PAUSED: {PluginState.STARTED, PluginState.STOPPED},
    PluginState.STOPPED: {PluginState.STARTED, PluginState.SHUTDOWN},
    PluginState.SHUTDOWN: set(),
}


class PluginInstance:
    """Wraps a ``PluginInfo`` with full lifecycle management.

    Lifecycle::

        plugin = PluginInstance(info, logger)
        await plugin.initialize()
        await plugin.start()
        await plugin.pause()
        await plugin.resume()
        await plugin.stop()
        await plugin.shutdown()

    """

    def __init__(
        self,
        info: PluginInfo,
        logger: Logger | None = None,
    ) -> None:
        """Wrap a ``PluginInfo`` for lifecycle management.

        Args:
            info: The plugin descriptor to manage.
            logger: Optional logger. Falls back to the default logger.

        """
        self._info = info
        self._logger = logger or get_logger()
        self._state = PluginState.CREATED

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Transition from ``CREATED`` to ``INITIALIZED``.

        Raises:
            PluginLifecycleError: If the current state does not allow
                initialization.

        """
        self._transition(PluginState.INITIALIZED)
        self._logger.info(
            "plugin.initialized",
            name=self._info.manifest.name,
            version=self._info.manifest.version,
        )

    async def start(self) -> None:
        """Transition from ``INITIALIZED`` to ``STARTED``.

        Raises:
            PluginLifecycleError: If the current state does not allow
                starting.

        """
        self._transition(PluginState.STARTED)
        self._logger.info(
            "plugin.started",
            name=self._info.manifest.name,
            version=self._info.manifest.version,
        )

    async def pause(self) -> None:
        """Transition from ``STARTED`` to ``PAUSED``.

        Raises:
            PluginLifecycleError: If the plugin is not currently
                running.

        """
        self._transition(PluginState.PAUSED)
        self._logger.info(
            "plugin.paused",
            name=self._info.manifest.name,
        )

    async def resume(self) -> None:
        """Transition from ``PAUSED`` back to ``STARTED``.

        Raises:
            PluginLifecycleError: If the plugin is not paused.

        """
        self._transition(PluginState.STARTED, allow_paused=True)
        self._logger.info(
            "plugin.resumed",
            name=self._info.manifest.name,
        )

    async def stop(self) -> None:
        """Transition from ``STARTED`` or ``PAUSED`` to ``STOPPED``.

        Raises:
            PluginLifecycleError: If the plugin is not in a running or
                paused state.

        """
        self._transition(PluginState.STOPPED)
        self._logger.info(
            "plugin.stopped",
            name=self._info.manifest.name,
        )

    async def shutdown(self) -> None:
        """Transition any non-terminal state to ``SHUTDOWN``.

        Raises:
            PluginLifecycleError: If already shut down.

        """
        if self._state is PluginState.SHUTDOWN:
            raise PluginLifecycleError(f"Plugin {self._info.manifest.name!r} is already shut down")
        self._state = PluginState.SHUTDOWN
        self._logger.info(
            "plugin.shutdown",
            name=self._info.manifest.name,
        )

    # ------------------------------------------------------------------
    # Publish helpers
    # ------------------------------------------------------------------

    async def publish_started(self, event_bus: EventBus) -> None:
        """Publish a ``plugin.started`` event for this plugin.

        Args:
            event_bus: The application event bus.

        """
        await event_bus.publish(
            Event(
                topic="plugin.started",
                data={
                    "name": self._info.manifest.name,
                    "version": self._info.manifest.version,
                },
            )
        )

    async def publish_stopped(self, event_bus: EventBus) -> None:
        """Publish a ``plugin.stopped`` event for this plugin.

        Args:
            event_bus: The application event bus.

        """
        await event_bus.publish(
            Event(
                topic="plugin.stopped",
                data={
                    "name": self._info.manifest.name,
                    "version": self._info.manifest.version,
                },
            )
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> PluginState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def info(self) -> PluginInfo:
        """Return the underlying ``PluginInfo``."""
        return self._info

    @property
    def config(self) -> dict[str, Any]:
        """Return the plugin's configuration dict."""
        return self._info.config

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition(self, target: PluginState, allow_paused: bool = False) -> None:
        """Validate and perform a state transition.

        Args:
            target: The target state.
            allow_paused: If ``True``, also allow transitions from
                ``PAUSED`` to the target.

        Raises:
            PluginLifecycleError: If the transition is invalid.

        """
        allowed = _TRANSITIONS.get(self._state, set())
        if target not in allowed:
            if allow_paused and self._state is PluginState.PAUSED:
                pass
            else:
                raise PluginLifecycleError(
                    f"Cannot transition plugin {self._info.manifest.name!r} "
                    f"from {self._state.value!r} to {target.value!r}"
                )
        self._state = target
