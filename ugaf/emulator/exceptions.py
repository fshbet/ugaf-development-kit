"""Exception hierarchy for the Emulator Manager subsystem."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "AvdAlreadyExistsError",
    "AvdNotFoundError",
    "EmulatorBootTimeoutError",
    "EmulatorCommandError",
    "EmulatorManagerError",
    "SdkNotFoundError",
    "SystemImageNotAvailableError",
]


class EmulatorManagerError(UGAFError):
    """Base exception for all Emulator Manager errors."""


class SdkNotFoundError(EmulatorManagerError):
    """Raised when the Android SDK or a required SDK tool cannot be located."""


class AvdNotFoundError(EmulatorManagerError):
    """Raised when an operation targets an AVD that does not exist."""


class AvdAlreadyExistsError(EmulatorManagerError):
    """Raised when creating an AVD whose name is already in use."""


class EmulatorCommandError(EmulatorManagerError):
    """Raised when an SDK tool invocation (``avdmanager``/``emulator``/``sdkmanager``) fails."""


class EmulatorBootTimeoutError(EmulatorManagerError):
    """Raised when an emulator instance does not finish booting within budget."""


class SystemImageNotAvailableError(EmulatorManagerError):
    """Raised when a requested Android system image is neither installed nor downloadable."""
