"""Exception hierarchy for the Emulator Manager subsystem."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ugaf.core.exceptions import UGAFError

if TYPE_CHECKING:
    from ugaf.emulator.boot_diagnostics import BootDiagnostics

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
    """Raised when an emulator instance does not finish booting within budget.

    Carries the exact stage that never completed and a snapshot of every
    boot signal collected up to the timeout (see
    :class:`~ugaf.android_platform.boot_diagnostics.BootDiagnostics`) --
    "did not finish booting" alone is exactly the unhelpful generic
    message this exception exists to replace (ADR-023).
    """

    def __init__(
        self,
        message: str,
        failed_stage: str | None = None,
        diagnostics: BootDiagnostics | None = None,
    ) -> None:
        """Record the message plus, when available, which stage failed and full diagnostics."""
        super().__init__(message)
        self.failed_stage = failed_stage
        self.diagnostics = diagnostics


class SystemImageNotAvailableError(EmulatorManagerError):
    """Raised when a requested Android system image is neither installed nor downloadable."""
