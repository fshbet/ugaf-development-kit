"""Tests for the ADB input provider.

``AdbInputProvider`` delegates device enumeration and shell execution
to :class:`~ugaf.device.adb_provider.AdbDeviceProvider`, so these tests
patch ``ugaf.device.adb_provider.subprocess.run`` (the actual call
site) rather than ``ugaf.input.adb.subprocess.run``. ``take_screenshot``
is the one operation not yet routed through the shared transport (ADB
``exec-out`` isn't a plain shell command), so its tests still patch
``ugaf.input.adb.subprocess.run`` directly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ugaf.input.adb import AdbInputProvider, _keycode
from ugaf.input.exceptions import ConnectionFailedError, DeviceNotFoundError


def _mock_subprocess(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


class TestKeycode:
    def test_known_key(self) -> None:
        assert _keycode("home") == 3

    def test_letter_key(self) -> None:
        assert _keycode("a") == 29
        assert _keycode("z") == 54

    def test_enter_key(self) -> None:
        assert _keycode("enter") == 66

    def test_space_key(self) -> None:
        assert _keycode("space") == 62

    def test_unknown_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown"):
            _keycode("nonexistent")


class TestConnect:
    def test_success_first_device(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess("List of devices attached\nemulator-5554\tdevice\n"),
                _mock_subprocess("Physical size: 1080x1920\n"),
            ]
            provider.connect()
        assert provider.is_connected() is True
        assert provider.device_id == "emulator-5554"
        assert provider.screen_size == (1080, 1920)

    def test_success_specific_device(self) -> None:
        provider = AdbInputProvider({"default_device": "abc123"})
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess("List of devices attached\nabc123\tdevice\n"),
                _mock_subprocess("Physical size: 720x1280\n"),
            ]
            provider.connect()
        assert provider.is_connected() is True
        assert provider.device_id == "abc123"

    def test_adb_not_available(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                returncode=1, stdout="", stderr="adb: command not found"
            )
            with pytest.raises(ConnectionFailedError):
                provider.connect()

    def test_adb_missing_binary_raises_connection_failed(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(ConnectionFailedError, match="not found"):
                provider.connect()

    def test_no_devices(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess("List of devices attached\n\n")
            with pytest.raises(DeviceNotFoundError, match="No Android devices"):
                provider.connect()

    def test_device_not_found(self) -> None:
        provider = AdbInputProvider({"default_device": "missing"})
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\nemulator-5554\tdevice\n"
            )
            with pytest.raises(DeviceNotFoundError, match="not found"):
                provider.connect()

    def test_configured_device_offline_among_others_reports_precise_status(self) -> None:
        """A device that isn't online gets a status-specific error, not a generic 'not found'."""
        provider = AdbInputProvider({"default_device": "abc123"})
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\nabc123\tunauthorized\nother-device\tdevice\n"
            )
            with pytest.raises(DeviceNotFoundError, match="is unauthorized"):
                provider.connect()

    def test_only_device_unauthorized_reports_in_status_summary(self) -> None:
        """When the requested device is the only one and it's not online, the 'no online
        devices' branch fires first — still with the correct status, just phrased
        differently from the 'other devices are online' case above.
        """
        provider = AdbInputProvider({"default_device": "abc123"})
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\nabc123\tunauthorized\n"
            )
            with pytest.raises(DeviceNotFoundError, match="abc123=unauthorized"):
                provider.connect()

    def test_no_online_devices_lists_their_actual_statuses(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess("List of devices attached\nabc123\toffline\n")
            with pytest.raises(DeviceNotFoundError, match="abc123=offline"):
                provider.connect()

    def test_connect_can_be_called_again_after_disconnect(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess("List of devices attached\nemulator-5554\tdevice\n"),
                _mock_subprocess("Physical size: 1080x1920\n"),
            ]
            provider.connect()
        provider.disconnect()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess("List of devices attached\nemulator-5554\tdevice\n"),
                _mock_subprocess("Physical size: 1080x1920\n"),
            ]
            provider.connect()
        assert provider.is_connected() is True


class TestDisconnect:
    def test_disconnect_resets_state(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        provider.disconnect()
        assert provider.is_connected() is False
        assert provider.device_id is None


class TestListDevices:
    def test_lists_only_online_devices(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\n"
                "emulator-5554\tdevice\n"
                "a1b2c3\tdevice\n"
                "offlinedev\toffline\n"
            )
            devices = provider.list_devices()
        assert devices == ["emulator-5554", "a1b2c3"]

    def test_adb_failure(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(returncode=1)
            with pytest.raises(ConnectionFailedError):
                provider.list_devices()


class TestClick:
    def test_tap(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.click(100, 200)
        args = mock_run.call_args[0][0]
        assert args[-5:] == ["shell", "input", "tap", "100", "200"]

    def test_raises_when_disconnected(self) -> None:
        provider = AdbInputProvider()
        with pytest.raises(ConnectionFailedError):
            provider.click(0, 0)

    def test_shell_failure_is_swallowed(self) -> None:
        """Input commands are fire-and-forget: a failed shell call does not raise."""
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(returncode=1, stderr="boom")
            provider.click(100, 200)  # should not raise


class TestDoubleClick:
    def test_two_taps(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            with patch("ugaf.input.adb.time.sleep"):
                provider.double_click(100, 200)
        assert mock_run.call_count == 2


class TestRightClick:
    def test_long_press_swipe(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.right_click(100, 200)
        args = mock_run.call_args[0][0]
        assert "swipe" in args
        assert "500" in args


class TestTypeText:
    def test_text_input(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.type_text("hello")
        args = mock_run.call_args[0][0]
        assert args[-3:] == ["input", "text", "hello"]

    def test_text_with_spaces(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.type_text("hello world")
        args = mock_run.call_args[0][0]
        assert args[-1] == "hello%sworld"


class TestPressKey:
    def test_keyevent(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.press_key("home")
        args = mock_run.call_args[0][0]
        assert args[-3:] == ["input", "keyevent", "3"]


class TestDrag:
    def test_swipe(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.drag(0, 0, 500, 1000, duration=0.5)
        args = mock_run.call_args[0][0]
        assert "swipe" in args
        assert "500" in args  # duration in ms


class TestScroll:
    def test_swipe_with_offset(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        provider._screen_width = 1080
        provider._screen_height = 1920
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.scroll(-3)
        args = mock_run.call_args[0][0]
        assert "swipe" in args


class TestScreenshot:
    def test_screenshot_returns_bytes(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"PNG...", returncode=0)
            result = provider.take_screenshot()
        assert result == b"PNG..."

    def test_screenshot_saves_to_file(self, tmp_path: Path) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        dest = tmp_path / "screenshot.png"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"PNG...", returncode=0)
            result = provider.take_screenshot(path=str(dest))
        assert result is None
        assert dest.read_bytes() == b"PNG..."


class TestWait:
    def test_sleep(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.input.adb.time.sleep") as mock_sleep:
            provider.wait(2.0)
            mock_sleep.assert_called_once_with(2.0)


class TestDependencyInjection:
    def test_accepts_shared_device_provider(self) -> None:
        """A provider can be constructed to reuse an existing AdbDeviceProvider
        (e.g. the one already owned by a DeviceManager) instead of creating its own.
        """
        from ugaf.device.adb_provider import AdbDeviceProvider

        shared = AdbDeviceProvider(executable="custom-adb")
        provider = AdbInputProvider(device_provider=shared)
        assert provider._device_provider is shared
