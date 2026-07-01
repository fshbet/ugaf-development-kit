"""Exception hierarchy for the Platform Abstraction Layer."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "AdapterNotAvailableError",
    "AdapterNotConnectedError",
    "PlatformLayerError",
]


class PlatformLayerError(UGAFError):
    """Base exception for all Platform Abstraction Layer errors."""


class AdapterNotAvailableError(PlatformLayerError):
    """Raised when a requested platform adapter is not registered or not usable.

    Covers both "no adapter registered under this name" and "the
    adapter is registered but its underlying OS dependency (a DLL, a
    binary, a library) is not available on this host".
    """


class AdapterNotConnectedError(PlatformLayerError):
    """Raised when an adapter operation is attempted before initialization."""
