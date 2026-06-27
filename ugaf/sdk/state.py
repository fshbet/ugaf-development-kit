"""Game state enumeration for UGAF game plugins."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "GameState",
]

# Valid state transitions for GameState.
_TRANSITIONS: dict[GameState, set[GameState]] = {}


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


_TRANSITIONS[GameState.CREATED] = {GameState.INITIALIZED, GameState.SHUTDOWN}
_TRANSITIONS[GameState.INITIALIZED] = {GameState.RUNNING, GameState.SHUTDOWN}
_TRANSITIONS[GameState.RUNNING] = {GameState.PAUSED, GameState.STOPPED}
_TRANSITIONS[GameState.PAUSED] = {GameState.RUNNING, GameState.STOPPED}
_TRANSITIONS[GameState.STOPPED] = {GameState.RUNNING, GameState.SHUTDOWN}
_TRANSITIONS[GameState.ERROR] = {GameState.CREATED, GameState.SHUTDOWN}
_TRANSITIONS[GameState.SHUTDOWN] = set()


def is_valid_transition(current: GameState, target: GameState) -> bool:
    """Check whether moving from *current* to *target* is allowed.

    Args:
        current: The current state.
        target: The desired target state.

    Returns:
        ``True`` if the transition is valid.

    """
    allowed = _TRANSITIONS.get(current, set())
    return target in allowed


def validate_transition(current: GameState, target: GameState) -> None:
    """Raise :class:`PluginStateError` if the transition is invalid.

    Args:
        current: The current state.
        target: The desired target state.

    Raises:
        PluginStateError: If the transition is not allowed.

    """
    if not is_valid_transition(current, target):
        from ugaf.sdk.exceptions import PluginStateError

        raise PluginStateError(f"Cannot transition from {current.value!r} to {target.value!r}")
