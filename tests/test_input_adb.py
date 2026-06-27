"""Tests for the ADB input provider."""

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
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
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
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess("List of devices attached\nabc123\tdevice\n"),
                _mock_subprocess("Physical size: 720x1280\n"),
            ]
            provider.connect()
        assert provider.is_connected() is True
        assert provider.device_id == "abc123"

    def test_adb_not_available(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                returncode=1, stdout="", stderr="adb: command not found"
            )
            with pytest.raises(ConnectionFailedError, match="ADB not available"):
                provider.connect()

    def test_no_devices(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess("List of devices attached\n\n")
            with pytest.raises(DeviceNotFoundError, match="No Android devices"):
                provider.connect()

    def test_device_not_found(self) -> None:
        provider = AdbInputProvider({"default_device": "missing"})
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\nemulator-5554\tdevice\n"
            )
            with pytest.raises(DeviceNotFoundError, match="not found"):
                provider.connect()

    def test_connect_retries_after_transport_error(self) -> None:
        provider = AdbInputProvider()
        call_count = 0

        def _side_effect(*args: object, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _mock_subprocess("List of devices attached\nemulator-5554\tdevice\n")
            if call_count == 2:
                return _mock_subprocess("Physical size: 1080x1920\n")
            return _mock_subprocess("")

        with patch("ugaf.input.adb.subprocess.run", side_effect=_side_effect):
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
    def test_lists_devices(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(
                "List of devices attached\nemulator-5554\tdevice\na1b2c3\tdevice\n"
            )
            devices = provider.list_devices()
        assert devices == ["emulator-5554", "a1b2c3"]

    def test_adb_failure(self) -> None:
        provider = AdbInputProvider()
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(returncode=1)
            with pytest.raises(ConnectionFailedError):
                provider.list_devices()


class TestClick:
    def test_tap(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            provider.click(100, 200)
        args = mock_run.call_args[0][0]
        assert args[-5:] == ["shell", "input", "tap", "100", "200"]

    def test_raises_when_disconnected(self) -> None:
        provider = AdbInputProvider()
        with pytest.raises(ConnectionFailedError):
            provider.click(0, 0)


class TestDoubleClick:
    def test_two_taps(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            with patch("ugaf.input.adb.time.sleep"):
                provider.double_click(100, 200)
        assert mock_run.call_count == 2


class TestRightClick:
    def test_long_press_swipe(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            provider.right_click(100, 200)
        args = mock_run.call_args[0][0]
        assert "swipe" in args
        assert "500" in args


class TestTypeText:
    def test_text_input(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            provider.type_text("hello")
        args = mock_run.call_args[0][0]
        assert args[-3:] == ["input", "text", "hello"]

    def test_text_with_spaces(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            provider.type_text("hello world")
        args = mock_run.call_args[0][0]
        assert args[-1] == "hello%sworld"


class TestPressKey:
    def test_keyevent(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
            provider.press_key("home")
        args = mock_run.call_args[0][0]
        assert args[-3:] == ["input", "keyevent", "3"]


class TestDrag:
    def test_swipe(self) -> None:
        provider = AdbInputProvider()
        provider._connected = True
        provider._device_id = "emulator-5554"
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
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
        with patch("ugaf.input.adb.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock()
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
