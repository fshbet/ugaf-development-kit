"""Tests for the display abstraction."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from ugaf.platform.display import DisplayInfo, WindowsDisplayProvider
from ugaf.platform.exceptions import AdapterNotAvailableError

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll")


def test_get_display_info_returns_landscape() -> None:
    provider = WindowsDisplayProvider()
    with (
        patch("ctypes.windll.user32.GetSystemMetrics", side_effect=[1920, 1080]),
        patch.object(provider, "_detect_scale_factor", return_value=1.25),
    ):
        info = provider.get_display_info()
    assert info == DisplayInfo(width=1920, height=1080, scale_factor=1.25, orientation="landscape")


def test_get_display_info_returns_portrait() -> None:
    provider = WindowsDisplayProvider()
    with (
        patch("ctypes.windll.user32.GetSystemMetrics", side_effect=[1080, 1920]),
        patch.object(provider, "_detect_scale_factor", return_value=1.0),
    ):
        info = provider.get_display_info()
    assert info.orientation == "portrait"


def test_get_display_info_raises_on_invalid_resolution() -> None:
    provider = WindowsDisplayProvider()
    with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=[0, 0]):
        with pytest.raises(AdapterNotAvailableError, match="invalid resolution"):
            provider.get_display_info()


def test_get_display_info_raises_on_os_error() -> None:
    provider = WindowsDisplayProvider()
    with patch("ctypes.windll.user32.GetSystemMetrics", side_effect=OSError("boom")):
        with pytest.raises(AdapterNotAvailableError, match="GetSystemMetrics failed"):
            provider.get_display_info()


def test_detect_scale_factor_falls_back_to_one_on_error() -> None:
    provider = WindowsDisplayProvider()
    with patch("ctypes.windll.shcore.GetScaleFactorForMonitor", side_effect=OSError("no shcore")):
        assert provider._detect_scale_factor() == 1.0


def test_detect_scale_factor_reads_shcore_value() -> None:
    provider = WindowsDisplayProvider()

    def _fake_get_scale_factor(_monitor: int, factor_ptr: MagicMock) -> None:
        factor_ptr._obj.value = 150  # noqa: SLF001

    with patch("ctypes.windll.shcore.GetScaleFactorForMonitor", side_effect=_fake_get_scale_factor):
        assert provider._detect_scale_factor() == 1.5
