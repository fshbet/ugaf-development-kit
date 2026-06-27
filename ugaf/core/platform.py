"""Platform detection for the UGAF framework."""

from __future__ import annotations

import platform as _platform
import sys
from dataclasses import dataclass

from ugaf.core.exceptions import PlatformError

__all__ = [
    "PlatformInfo",
    "detect_platform",
]


@dataclass(frozen=True)
class PlatformInfo:
    """Detected platform information.

    Attributes:
        system: Operating system name (``"Windows"``, ``"Linux"``,
            ``"Darwin"``).
        is_wsl: Whether running under Windows Subsystem for Linux.
        is_64bit: Whether the Python interpreter is 64-bit.
        python_version: Python version string (e.g. ``"3.13.0"``).
        machine: Machine type (e.g. ``"AMD64"``, ``"x86_64"``).
        processor: Processor name.
        release: OS release string.

    """

    system: str
    is_wsl: bool
    is_64bit: bool
    python_version: str
    machine: str
    processor: str
    release: str

    @property
    def is_windows(self) -> bool:
        """Return ``True`` if running on Windows."""
        return self.system == "Windows"

    @property
    def is_linux(self) -> bool:
        """Return ``True`` if running on Linux (including WSL)."""
        return self.system == "Linux"

    @property
    def is_macos(self) -> bool:
        """Return ``True`` if running on macOS."""
        return self.system == "Darwin"


def _check_wsl() -> bool:
    """Detect whether running under Windows Subsystem for Linux.

    Uses the presence of ``"microsoft"`` or ``"wsl"`` in
    ``/proc/version``.

    Returns:
        ``True`` if WSL is detected.

    """
    if sys.platform != "linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as fh:
            content = fh.read().lower()
        return "microsoft" in content or "wsl" in content
    except OSError:
        return False


def detect_platform() -> PlatformInfo:
    """Detect the current platform and return detailed information.

    Returns:
        A frozen ``PlatformInfo`` dataclass with detected values.

    Raises:
        PlatformError: If platform detection encounters an unexpected
            error.

    """
    try:
        return PlatformInfo(
            system=_platform.system(),
            is_wsl=_check_wsl(),
            is_64bit=sys.maxsize > 2**32,
            python_version=_platform.python_version(),
            machine=_platform.machine(),
            processor=_platform.processor(),
            release=_platform.release(),
        )
    except OSError as exc:
        raise PlatformError(f"Platform detection failed: {exc}") from exc
