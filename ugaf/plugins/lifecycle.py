"""Lifecycle wrapper for UGAF game plugins.

Each :class:`PluginLifecycle` wraps a :class:`~ugaf.sdk.game.GamePlugin`
instance and manages its :class:`~ugaf.sdk.state.GameState` transitions,
event publishing, and error handling.

"""

from __future__ import annotations

from typing import Any

from ugaf.core.event_bus import Event, EventBus
from ugaf.core.logger import Logger, get_logger
from ugaf.sdk.context import GameContext
from ugaf.sdk.events import (
    PLUGIN_FAILED,
    PLUGIN_INITIALIZED,
    PLUGIN_PAUSED,
    PLUGIN_SHUTDOWN,
    PLUGIN_STARTED,
    PLUGIN_STOPPED,
)
from ugaf.sdk.exceptions import PluginStateError
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState

__all__ = [
    "PluginLifecycle",
]

_EVENT_MAP: dict[GameState, str] = {
    GameState.INITIALIZED: PLUGIN_INITIALIZED,
    GameState.RUNNING: PLUGIN_STARTED,
    GameState.PAUSED: PLUGIN_PAUSED,
    GameState.STOPPED: PLUGIN_STOPPED,
    GameState.SHUTDOWN: PLUGIN_SHUTDOWN,
}


class PluginLifecycle:
    """Manages state transitions and event publishing for a plugin.

    Usage::

        lifecycle = PluginLifecycle(plugin, metadata, event_bus, logger)
        await lifecycle.initialize(context)
        await lifecycle.start()
        await lifecycle.stop()
        await lifecycle.shutdown()

    """

    def __init__(
        self,
        plugin: GamePlugin,
        metadata: PluginMetadata,
        event_bus: EventBus,
        logger: Logger | None = None,
    ) -> None:
        """Wrap a game plugin with lifecycle management.

        Args:
            plugin: The game plugin instance.
            metadata: The plugin's metadata.
            event_bus: The application event bus.
            logger: Optional logger.

        """
        self._plugin = plugin
        self._metadata = metadata
        self._event_bus = event_bus
        self._logger = logger or get_logger()
        self._state = GameState.CREATED

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> GameState:
        """Return the current lifecycle state."""
        return self._state

    @property
    def plugin(self) -> GamePlugin:
        """Return the underlying game plugin."""
        return self._plugin

    @property
    def metadata(self) -> PluginMetadata:
        """Return the plugin metadata."""
        return self._metadata

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    async def initialize(self, context: GameContext) -> None:
        """Transition from CREATED to INITIALIZED.

        Args:
            context: The game context for the plugin.

        Raises:
            PluginStateError: If the transition is invalid.

        """
        self._transition(GameState.INITIALIZED)
        try:
            await self._plugin.initialize(context)
        except Exception as exc:
            self._state = GameState.ERROR
            await self._publish_error("initialize", exc)
            raise
        await self._publish_state_event()

    async def start(self) -> None:
        """Transition from INITIALIZED to RUNNING.

        Raises:
            PluginStateError: If the transition is invalid.

        """
        self._transition(GameState.RUNNING)
        try:
            await self._plugin.start()
        except Exception as exc:
            self._state = GameState.ERROR
            await self._publish_error("start", exc)
            raise
        await self._publish_state_event()

    async def pause(self) -> None:
        """Transition from RUNNING to PAUSED.

        Raises:
            PluginStateError: If the plugin is not running.

        """
        current_state = self._state
        self._transition(GameState.PAUSED)
        try:
            await self._plugin.pause()
        except Exception as exc:
            if current_state is not None:
                self._state = current_state
            await self._publish_error("pause", exc)
            raise
        await self._publish_state_event()

    async def resume(self) -> None:
        """Transition from PAUSED to RUNNING.

        Raises:
            PluginStateError: If the plugin is not paused.

        """
        self._transition(GameState.RUNNING)
        try:
            await self._plugin.resume()
        except Exception as exc:
            self._state = GameState.PAUSED
            await self._publish_error("resume", exc)
            raise
        await self._publish_state_event()

    async def stop(self) -> None:
        """Transition from RUNNING or PAUSED to STOPPED.

        Raises:
            PluginStateError: If the plugin is not in a stoppable
                state.

        """
        self._transition(GameState.STOPPED)
        try:
            await self._plugin.stop()
        except Exception as exc:
            self._state = GameState.ERROR
            await self._publish_error("stop", exc)
            raise
        await self._publish_state_event()

    async def shutdown(self) -> None:
        """Transition to SHUTDOWN (terminal state).

        Raises:
            PluginStateError: If already shut down.

        """
        if self._state is GameState.SHUTDOWN:
            raise PluginStateError(f"Plugin {self._metadata.name!r} is already shut down")
        self._state = GameState.SHUTDOWN
        try:
            await self._plugin.shutdown()
        except Exception as exc:
            self._logger.error(
                "plugin.shutdown_failed",
                plugin=self._metadata.id,
                error=str(exc),
            )
        await self._publish_state_event()

    async def health(self) -> dict[str, Any]:
        """Return the plugin's health status.

        Returns:
            Health dictionary with at least ``"status"`` and
            ``"state"`` keys.

        """
        try:
            result = await self._plugin.health()
        except Exception as exc:
            return {
                "status": "error",
                "state": self._state.value,
                "error": str(exc),
            }
        if isinstance(result, dict):
            result["state"] = self._state.value
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _transition(self, target: GameState) -> None:
        """Validate and apply a state transition."""
        self._state.validate_transition(target)
        self._state = target

    async def _publish_state_event(self) -> None:
        """Publish the event corresponding to the current state."""
        event_topic = _EVENT_MAP.get(self._state)
        if event_topic is not None:
            await self._event_bus.publish(
                Event(
                    topic=event_topic,
                    data={
                        "plugin_id": self._metadata.id,
                        "name": self._metadata.name,
                        "version": self._metadata.version,
                        "state": self._state.value,
                    },
                )
            )

    async def _publish_error(self, operation: str, exc: Exception) -> None:
        """Publish a plugin.failed event."""
        await self._event_bus.publish(
            Event(
                topic=PLUGIN_FAILED,
                data={
                    "plugin_id": self._metadata.id,
                    "name": self._metadata.name,
                    "operation": operation,
                    "error": str(exc),
                    "state": self._state.value,
                },
            )
        )
