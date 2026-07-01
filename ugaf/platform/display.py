"""Display information abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ugaf.platform.exceptions import AdapterNotAvailableError

__all__ = [
    "DisplayInfo",
    "DisplayProvider",
    "WindowsDisplayProvider",
]


@dataclass(frozen=True)
class DisplayInfo:
    """Snapshot of the primary display's geometry.

    Attributes:
        width: Primary display width in pixels.
        height: Primary display height in pixels.
        scale_factor: DPI scale factor (``1.0`` = 96 DPI / 100%).
        orientation: ``"landscape"`` if width >= height, else
            ``"portrait"``.

    """

    width: int
    height: int
    scale_factor: float
    orientation: str


class DisplayProvider(ABC):
    """Abstract interface for querying the primary display."""

    @abstractmethod
    def get_display_info(self) -> DisplayInfo:
        """Return the current primary display's geometry.

        Raises:
            AdapterNotAvailableError: If the underlying OS API is
                unavailable on this host.

        """


class WindowsDisplayProvider(DisplayProvider):
    """Display provider backed by the Win32 ``user32``/``shcore`` APIs via ``ctypes``.

    Uses ``GetSystemMetrics`` for resolution and
    ``GetScaleFactorForDevice`` (Shcore, Windows 8.1+) for DPI scaling,
    falling back to a scale factor of ``1.0`` if unavailable.
    """

    _SM_CXSCREEN = 0
    _SM_CYSCREEN = 1

    def get_display_info(self) -> DisplayInfo:
        """Query the primary display via ``ctypes.windll``.

        Raises:
            AdapterNotAvailableError: If not running on Windows or the
                Win32 API call fails.

        """
        try:
            import ctypes
        except ImportError as exc:  # pragma: no cover - ctypes is stdlib
            raise AdapterNotAvailableError("ctypes is not available") from exc

        user32 = getattr(ctypes, "windll", None)
        if user32 is None:
            raise AdapterNotAvailableError(
                "WindowsDisplayProvider requires Windows (ctypes.windll)"
            )

        try:
            width = ctypes.windll.user32.GetSystemMetrics(self._SM_CXSCREEN)
            height = ctypes.windll.user32.GetSystemMetrics(self._SM_CYSCREEN)
        except OSError as exc:
            raise AdapterNotAvailableError(f"GetSystemMetrics failed: {exc}") from exc

        if width <= 0 or height <= 0:
            raise AdapterNotAvailableError("GetSystemMetrics returned an invalid resolution")

        scale_factor = self._detect_scale_factor()
        orientation = "landscape" if width >= height else "portrait"
        return DisplayInfo(
            width=width,
            height=height,
            scale_factor=scale_factor,
            orientation=orientation,
        )

    def _detect_scale_factor(self) -> float:
        """Best-effort DPI scale factor lookup; defaults to ``1.0``."""
        try:
            import ctypes

            shcore = ctypes.windll.shcore
            factor = ctypes.c_int()
            # MDT_EFFECTIVE_DPI = 0, monitor handle 0 = primary
            shcore.GetScaleFactorForMonitor(0, ctypes.byref(factor))
            if factor.value > 0:
                return factor.value / 100.0
        except (OSError, AttributeError, ValueError):
            pass
        return 1.0
