"""Windows window-capture provider — a capture transport for emulators.

Captures a specific window's client area directly (via ``mss`` +
``pywin32``) instead of going through ADB's ``screencap``. Intended
for Android emulators that run as ordinary Windows application windows
(BlueStacks, NoxPlayer, LDPlayer, the Android Studio emulator, ...) —
this replaces only the *frame source*. ADB (or whichever transport the
emulator exposes) remains the transport for device discovery, input
injection, application lifecycle, and shell commands, per
``ARCHITECTURE.md``; ``VisionManager`` consumes whatever
:class:`~ugaf.vision.screenshot.ScreenshotProvider` it is given without
knowing this one isn't ADB-backed.

Requires the optional ``mss``/``pywin32`` dependencies
(``pip install ugaf[emulator]``) — importing this module never fails
even if they are missing; only actually capturing does, with a clear
error naming the missing package.
"""

from __future__ import annotations

from typing import Any

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

__all__ = [
    "WindowCaptureProvider",
]


class WindowCaptureProvider(ScreenshotProvider):
    """Captures a named window's client area as the frame source.

    Usage::

        provider = WindowCaptureProvider(imaging, window_title="BlueStacks App Player")
        frame = provider.capture_full()

    """

    def __init__(self, imaging: ImagingManager, window_title: str) -> None:
        """Bind to a window by (exact or substring) title.

        Args:
            imaging: Used to wrap captured pixel data as an
                :class:`~ugaf.imaging.image.Image`.
            window_title: The target window's title. Matched exactly
                first; falls back to a case-insensitive substring match
                across visible top-level windows (so "BlueStacks" finds
                "BlueStacks App Player").

        """
        self._imaging = imaging
        self._window_title = window_title

    def capture_full(self) -> Image:
        """Capture the bound window's client area.

        Raises:
            ScreenshotError: If ``pywin32``/``mss`` are not installed,
                no matching window is found, or the capture fails.

        """
        win32gui = _import_win32gui()
        hwnd = _find_window(win32gui, self._window_title)
        left, top, right, bottom = _client_rect_on_screen(win32gui, hwnd)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise ScreenshotError(
                f"Window {self._window_title!r} has an empty client area "
                f"(minimized or zero-sized)"
            )
        return self._grab(left, top, width, height)

    def capture_region(self, region: Region) -> Image:
        """Capture *region*, relative to the window's client area."""
        win32gui = _import_win32gui()
        hwnd = _find_window(win32gui, self._window_title)
        left, top, _, _ = _client_rect_on_screen(win32gui, hwnd)
        return self._grab(left + region.x, top + region.y, region.width, region.height)

    def capture_game_window(self, window_title: str) -> Image:
        """Capture *window_title* directly, without needing a second provider instance."""
        win32gui = _import_win32gui()
        hwnd = _find_window(win32gui, window_title)
        left, top, right, bottom = _client_rect_on_screen(win32gui, hwnd)
        return self._grab(left, top, right - left, bottom - top)

    def _grab(self, left: int, top: int, width: int, height: int) -> Image:
        """Grab a screen region via ``mss`` and wrap it as an :class:`Image`."""
        try:
            import mss
        except ImportError as exc:
            raise ScreenshotError(
                "WindowCaptureProvider requires 'mss' — install via "
                "`pip install ugaf[emulator]`"
            ) from exc
        import numpy

        with mss.mss() as sct:
            shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        # mss yields BGRA; drop the alpha channel to match the project's BGR
        # image convention (the same layout AdbScreenshotProvider produces).
        data = numpy.array(shot)[:, :, :3]
        return Image(data, self._imaging.backend)


def _import_win32gui() -> Any:
    """Import ``win32gui``, raising a clear :class:`ScreenshotError` if unavailable."""
    try:
        import win32gui

        return win32gui
    except ImportError as exc:
        raise ScreenshotError(
            "WindowCaptureProvider requires 'pywin32' — install via `pip install ugaf[emulator]`"
        ) from exc


def _find_window(win32gui: Any, title: str) -> int:
    """Return the window handle matching *title*, exact then substring.

    Raises:
        ScreenshotError: If no visible window matches.

    """
    hwnd = win32gui.FindWindow(None, title)
    if hwnd:
        return int(hwnd)

    lowered = title.lower()
    matches: list[int] = []

    def _on_window(handle: int, _: object) -> None:
        if win32gui.IsWindowVisible(handle) and lowered in win32gui.GetWindowText(handle).lower():
            matches.append(handle)

    win32gui.EnumWindows(_on_window, None)
    if matches:
        return matches[0]

    raise ScreenshotError(f"No visible window found matching title {title!r}")


def _client_rect_on_screen(win32gui: Any, hwnd: int) -> tuple[int, int, int, int]:
    """Return a window's client area as absolute screen coordinates.

    Returns ``(left, top, right, bottom)``.
    """
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (left, top))
    right, bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return left, top, right, bottom
