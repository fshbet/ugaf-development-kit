"""Game state enumeration for UGAF game plugins."""

from __future__ import annotations

from enum import Enum

from ugaf.sdk.exceptions import PluginStateError

__all__ = [
    "GameState",
]


class GameState(Enum):
    """Lifecycle state of a game plugin instance.

    Attributes:
        CREATED: Plugin discovered but not yet initialized.
        INITIALIZED: Plugin has been initialized and is ready to start.
        RUNNING: Plugin is actively running.
        PAUSED: Plugin has been temporarily paused.
        STOPPED: Plugin has been stopped (can be restarted).
        ERROR: Plugin encountered a runtime error.
        SHUTDOWN: Plugin has been shut down (terminal state).

    """

    CREATED = "created"
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"
    SHUTDOWN = "shutdown"

    def can_transition_to(self, target: GameState) -> bool:
        """Check whether moving from *self* to *target* is allowed.

        Args:
            target: The desired target state.

        Returns:
            ``True`` if the transition is valid.

        """
        allowed = _TRANSITIONS.get(self, set())
        return target in allowed

    def validate_transition(self, target: GameState) -> None:
        """Raise :class:`PluginStateError` if the transition is invalid.

        Args:
            target: The desired target state.

        Raises:
            PluginStateError: If the transition is not allowed.

        """
        if not self.can_transition_to(target):
            raise PluginStateError(f"Cannot transition from {self.value!r} to {target.value!r}")


_TRANSITIONS: dict[GameState, set[GameState]] = {
    GameState.CREATED: {GameState.INITIALIZED, GameState.SHUTDOWN},
    GameState.INITIALIZED: {GameState.RUNNING, GameState.SHUTDOWN},
    GameState.RUNNING: {GameState.PAUSED, GameState.STOPPED},
    GameState.PAUSED: {GameState.RUNNING, GameState.STOPPED},
    GameState.STOPPED: {GameState.RUNNING, GameState.SHUTDOWN},
    GameState.ERROR: {GameState.CREATED, GameState.SHUTDOWN},
    GameState.SHUTDOWN: set(),
}
