"""Exception hierarchy for the Device Manager subsystem."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "DeviceCommandError",
    "DeviceManagerError",
    "DeviceNotConnectedError",
    "TransportUnavailableError",
]


class DeviceManagerError(UGAFError):
    """Base exception for all Device Manager errors."""


class TransportUnavailableError(DeviceManagerError):
    """Raised when a transport's backing tool (e.g. the ``adb`` binary) is unavailable."""


class DeviceNotConnectedError(DeviceManagerError):
    """Raised when an operation targets a device that is not currently online."""


class DeviceCommandError(DeviceManagerError):
    """Raised when a command executed on a device fails after all retries."""
