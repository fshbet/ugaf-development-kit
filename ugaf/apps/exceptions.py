"""Exception hierarchy for the Application Manager subsystem."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "AppLaunchError",
    "AppManagerError",
    "AppNotInstalledError",
]


class AppManagerError(UGAFError):
    """Base exception for all Application Manager errors."""


class AppNotInstalledError(AppManagerError):
    """Raised when an operation targets a package not installed on the device."""


class AppLaunchError(AppManagerError):
    """Raised when an application cannot be launched or confirmed ready."""
