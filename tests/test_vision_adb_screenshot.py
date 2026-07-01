"""Tests for AdbScreenshotProvider."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ugaf.imaging.exceptions import ImageLoadError
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.adb_screenshot import AdbScreenshotProvider
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region


@pytest.fixture
def imaging() -> ImagingManager:
    return MagicMock(spec=ImagingManager)


def _mock_result(stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


class TestCaptureFull:
    def test_success_with_explicit_device(self, imaging: ImagingManager) -> None:
        fake_image = MagicMock()
        imaging.from_bytes.return_value = fake_image  # type: ignore[attr-defined]
        provider = AdbScreenshotProvider(imaging, device_id="emulator-5554")

        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(stdout=b"PNGDATA")
            result = provider.capture_full()

        assert result is fake_image
        imaging.from_bytes.assert_called_once_with(b"PNGDATA")  # type: ignore[attr-defined]
        args = mock_run.call_args[0][0]
        assert args == ["adb", "-s", "emulator-5554", "exec-out", "screencap", "-p"]

    def test_picks_first_online_device_when_unset(self, imaging: ImagingManager) -> None:
        from ugaf.platform.device import DeviceInfo, DeviceStatus

        device_provider = MagicMock()
        device_provider.list_devices.return_value = [
            DeviceInfo(
                id="offline1",
                name="x",
                status=DeviceStatus.OFFLINE,
                platform="android",
                transport="adb",
            ),
            DeviceInfo(
                id="online1",
                name="x",
                status=DeviceStatus.ONLINE,
                platform="android",
                transport="adb",
            ),
        ]
        provider = AdbScreenshotProvider(imaging, device_provider=device_provider)

        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(stdout=b"PNGDATA")
            provider.capture_full()

        args = mock_run.call_args[0][0]
        assert args[2] == "online1"

    def test_no_online_devices_raises(self, imaging: ImagingManager) -> None:
        device_provider = MagicMock()
        device_provider.list_devices.return_value = []
        provider = AdbScreenshotProvider(imaging, device_provider=device_provider)

        with pytest.raises(ScreenshotError, match="No online Android devices"):
            provider.capture_full()

    def test_adb_missing_binary_raises(self, imaging: ImagingManager) -> None:
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with patch("ugaf.vision.adb_screenshot.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(ScreenshotError, match="not found"):
                provider.capture_full()

    def test_timeout_raises(self, imaging: ImagingManager) -> None:
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with patch(
            "ugaf.vision.adb_screenshot.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=30),
        ):
            with pytest.raises(ScreenshotError, match="timed out"):
                provider.capture_full()

    def test_nonzero_exit_raises(self, imaging: ImagingManager) -> None:
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(returncode=1, stderr=b"no device")
            with pytest.raises(ScreenshotError, match="screencap failed"):
                provider.capture_full()

    def test_empty_stdout_raises(self, imaging: ImagingManager) -> None:
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(stdout=b"")
            with pytest.raises(ScreenshotError, match="screencap failed"):
                provider.capture_full()

    def test_decode_failure_raises(self, imaging: ImagingManager) -> None:
        imaging.from_bytes.side_effect = ImageLoadError("bad png")  # type: ignore[attr-defined]
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(stdout=b"garbage")
            with pytest.raises(ScreenshotError, match="Failed to decode"):
                provider.capture_full()


class TestCaptureRegion:
    def test_crops_full_capture(self, imaging: ImagingManager) -> None:
        fake_image = MagicMock()
        cropped = MagicMock()
        fake_image.crop.return_value = cropped
        imaging.from_bytes.return_value = fake_image  # type: ignore[attr-defined]
        provider = AdbScreenshotProvider(imaging, device_id="dev1")

        with patch("ugaf.vision.adb_screenshot.subprocess.run") as mock_run:
            mock_run.return_value = _mock_result(stdout=b"PNGDATA")
            result = provider.capture_region(Region(10, 20, 100, 200))

        fake_image.crop.assert_called_once_with(10, 20, 100, 200)
        assert result is cropped


class TestCaptureGameWindow:
    def test_not_supported(self, imaging: ImagingManager) -> None:
        provider = AdbScreenshotProvider(imaging, device_id="dev1")
        with pytest.raises(ScreenshotError, match="not supported"):
            provider.capture_game_window("Some Window")
