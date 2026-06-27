"""SDK exceptions for UGAF game plugins."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "GameSDKError",
    "PluginStateError",
    "PluginValidationError",
]


class GameSDKError(UGAFError):
    """Base exception for all Game SDK errors."""


class PluginValidationError(GameSDKError):
    """Raised when plugin validation fails."""


class PluginStateError(GameSDKError):
    """Raised when an invalid state transition is attempted."""
