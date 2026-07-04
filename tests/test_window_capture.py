"""Tests for ugaf.vision.window_capture.WindowCaptureProvider.

pywin32/mss are optional dependencies not necessarily installed in
every environment, so these tests inject fake modules via
``sys.modules`` rather than requiring them — this also lets us assert
exactly how WindowCaptureProvider calls into the Win32 API without a
real window.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import numpy
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.window_capture import WindowCaptureProvider


@pytest.fixture
def imaging() -> ImagingManager:
    from unittest.mock import MagicMock

    mgr = MagicMock(spec=ImagingManager)
    mgr.backend = MagicMock(spec=ImageBackend)
    return mgr


class _FakeWin32Gui:
    """Stand-in for the win32gui module, scriptable per test."""

    def __init__(
        self, windows: dict[int, str], client_rects: dict[int, tuple[int, int, int, int]]
    ):
        self._windows = windows
        self._client_rects = client_rects
        self.exact_lookup: dict[str, int] = {}

    def FindWindow(self, _class_name: object, title: str) -> int:  # noqa: N802
        return self.exact_lookup.get(title, 0)

    def IsWindowVisible(self, hwnd: int) -> bool:  # noqa: N802
        return hwnd in self._windows

    def GetWindowText(self, hwnd: int) -> str:  # noqa: N802
        return self._windows.get(hwnd, "")

    def EnumWindows(self, callback: Any, extra: object) -> None:  # noqa: N802
        for hwnd in self._windows:
            callback(hwnd, extra)

    def GetClientRect(self, hwnd: int) -> tuple[int, int, int, int]:  # noqa: N802
        rect = self._client_rects[hwnd]
        return (0, 0, rect[2] - rect[0], rect[3] - rect[1])

    def ClientToScreen(self, hwnd: int, point: tuple[int, int]) -> tuple[int, int]:  # noqa: N802
        left, top, _, _ = self._client_rects[hwnd]
        x, y = point
        return (left + x, top + y)


def _install_fake_win32gui(monkeypatch: pytest.MonkeyPatch, fake: _FakeWin32Gui) -> None:
    module = types.ModuleType("win32gui")
    for name in ("FindWindow", "IsWindowVisible", "GetWindowText", "EnumWindows",
                 "GetClientRect", "ClientToScreen"):
        setattr(module, name, getattr(fake, name))
    monkeypatch.setitem(sys.modules, "win32gui", module)


def _install_fake_mss(
    monkeypatch: pytest.MonkeyPatch, pixel: tuple[int, int, int, int]
) -> dict[str, Any]:
    """Install a fake mss module; returns the dict of the last grab() region requested."""
    captured_region: dict[str, Any] = {}

    class _FakeShot:
        def __init__(self, region: dict[str, int]) -> None:
            height, width = region["height"], region["width"]
            self.size = (width, height)
            self._array = numpy.full((height, width, 4), pixel, dtype=numpy.uint8)

        def __array__(self, dtype: object = None, copy: object = None) -> numpy.ndarray:
            return self._array

    class _FakeMSS:
        def __enter__(self) -> _FakeMSS:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def grab(self, region: dict[str, int]) -> _FakeShot:
            captured_region.update(region)
            return _FakeShot(region)

    module = types.ModuleType("mss")
    module.mss = _FakeMSS  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mss", module)
    return captured_region


def test_capture_full_finds_exact_title_and_returns_client_area(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gui = _FakeWin32Gui(
        windows={42: "BlueStacks App Player"},
        client_rects={42: (100, 200, 100 + 540, 200 + 960)},
    )
    fake_gui.exact_lookup["BlueStacks App Player"] = 42
    _install_fake_win32gui(monkeypatch, fake_gui)
    region = _install_fake_mss(monkeypatch, pixel=(10, 20, 30, 255))

    provider = WindowCaptureProvider(imaging, window_title="BlueStacks App Player")
    image = provider.capture_full()

    assert isinstance(image, Image)
    assert region == {"left": 100, "top": 200, "width": 540, "height": 960}
    assert image.data.shape == (960, 540, 3)  # alpha channel dropped


def test_capture_full_falls_back_to_substring_match(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gui = _FakeWin32Gui(
        windows={7: "NoxPlayer - Untitled"},
        client_rects={7: (0, 0, 400, 700)},
    )
    # No exact match registered -> must fall back to substring search.
    _install_fake_win32gui(monkeypatch, fake_gui)
    _install_fake_mss(monkeypatch, pixel=(0, 0, 0, 255))

    provider = WindowCaptureProvider(imaging, window_title="noxplayer")
    image = provider.capture_full()
    assert image.data.shape == (700, 400, 3)


def test_no_matching_window_raises_clear_error(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gui = _FakeWin32Gui(windows={}, client_rects={})
    _install_fake_win32gui(monkeypatch, fake_gui)

    provider = WindowCaptureProvider(imaging, window_title="Nonexistent Emulator")
    with pytest.raises(ScreenshotError, match="No visible window"):
        provider.capture_full()


def test_missing_pywin32_raises_actionable_error(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "win32gui", None)  # simulate ImportError
    provider = WindowCaptureProvider(imaging, window_title="Anything")
    with pytest.raises(ScreenshotError, match="pywin32"):
        provider.capture_full()


def test_capture_region_offsets_from_window_client_area(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ugaf.vision.region import Region

    fake_gui = _FakeWin32Gui(
        windows={1: "Emulator"},
        client_rects={1: (50, 60, 50 + 800, 60 + 600)},
    )
    fake_gui.exact_lookup["Emulator"] = 1
    _install_fake_win32gui(monkeypatch, fake_gui)
    region = _install_fake_mss(monkeypatch, pixel=(1, 2, 3, 255))

    provider = WindowCaptureProvider(imaging, window_title="Emulator")
    provider.capture_region(Region(x=10, y=20, width=100, height=50))

    assert region == {"left": 60, "top": 80, "width": 100, "height": 50}


def test_empty_client_area_raises_clear_error(
    imaging: ImagingManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_gui = _FakeWin32Gui(
        windows={9: "Minimized Emulator"},
        client_rects={9: (0, 0, 0, 0)},
    )
    fake_gui.exact_lookup["Minimized Emulator"] = 9
    _install_fake_win32gui(monkeypatch, fake_gui)

    provider = WindowCaptureProvider(imaging, window_title="Minimized Emulator")
    with pytest.raises(ScreenshotError, match="empty client area"):
        provider.capture_full()
