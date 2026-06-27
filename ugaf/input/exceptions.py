"""Input engine exception hierarchy for the UGAF framework."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "ConnectionFailedError",
    "CoordinateOutOfBoundsError",
    "DeviceNotFoundError",
    "InputError",
    "ProviderNotAvailableError",
]


class InputError(UGAFError):
    """Base exception for all input engine errors."""


class DeviceNotFoundError(InputError):
    """Raised when a target device cannot be found."""


class ProviderNotAvailableError(InputError):
    """Raised when the requested input provider is not available."""


class ConnectionFailedError(InputError):
    """Raised when connecting to an input provider fails."""


class CoordinateOutOfBoundsError(InputError):
    """Raised when coordinates fall outside the screen bounds."""
