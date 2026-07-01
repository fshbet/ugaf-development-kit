"""Tests for AdbDeviceProvider."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from ugaf.device.adb_provider import AdbDeviceProvider
from ugaf.device.exceptions import DeviceCommandError, TransportUnavailableError
from ugaf.platform.device import DeviceStatus


def _mock_subprocess(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


_DEVICES_L_OUTPUT = (
    "List of devices attached\n"
    "emulator-5554          device product:sdk_gphone64_x86_64 model:Pixel_7 "
    "device:emulator64_x86_64 transport_id:1\n"
    "ABC123OFFLINE          offline transport_id:2\n"
    "XYZ456UNAUTH           unauthorized transport_id:3\n"
    "\n"
)


class TestListDevices:
    def test_parses_online_offline_unauthorized(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(_DEVICES_L_OUTPUT)
            devices = provider.list_devices()

        by_id = {d.id: d for d in devices}
        assert by_id["emulator-5554"].status is DeviceStatus.ONLINE
        assert by_id["emulator-5554"].name == "Pixel_7"
        assert by_id["emulator-5554"].platform == "android"
        assert by_id["emulator-5554"].transport == "adb"
        assert by_id["ABC123OFFLINE"].status is DeviceStatus.OFFLINE
        assert by_id["XYZ456UNAUTH"].status is DeviceStatus.UNAUTHORIZED

    def test_empty_device_list(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess("List of devices attached\n\n")
            assert provider.list_devices() == []

    def test_unknown_state_maps_to_unknown_status(self) -> None:
        provider = AdbDeviceProvider()
        output = "List of devices attached\nWEIRD001               bootloader\n"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(output)
            devices = provider.list_devices()
        assert devices[0].status is DeviceStatus.UNKNOWN
        assert devices[0].extra["raw_state"] == "bootloader"

    def test_adb_missing_raises_transport_unavailable(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(TransportUnavailableError, match="not found"):
                provider.list_devices()

    def test_adb_timeout_raises_transport_unavailable(self) -> None:
        provider = AdbDeviceProvider()
        with patch(
            "ugaf.device.adb_provider.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="adb", timeout=10),
        ):
            with pytest.raises(TransportUnavailableError, match="timed out"):
                provider.list_devices()


class TestGetDevice:
    def test_get_device_found(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(_DEVICES_L_OUTPUT)
            device = provider.get_device("emulator-5554")
        assert device is not None
        assert device.status is DeviceStatus.ONLINE

    def test_get_device_not_found(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(_DEVICES_L_OUTPUT)
            assert provider.get_device("missing") is None


class TestGetProperties:
    def test_parses_getprop_output(self) -> None:
        provider = AdbDeviceProvider()
        output = "[ro.build.version.release]: [14]\n[ro.product.model]: [Pixel 7]\n"
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(output)
            props = provider.get_properties("emulator-5554")
        assert props["ro.build.version.release"] == "14"
        assert props["ro.product.model"] == "Pixel 7"

    def test_returns_empty_dict_on_command_failure(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(returncode=1, stderr="no device")
            assert provider.get_properties("missing") == {}

    def test_returns_empty_dict_when_adb_missing(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run", side_effect=FileNotFoundError):
            assert provider.get_properties("emulator-5554") == {}


class TestShell:
    def test_shell_returns_stdout(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess("1080x1920\n")
            output = provider.shell("emulator-5554", "wm", "size")
        assert output == "1080x1920\n"

    def test_shell_raises_on_failure(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess(returncode=1, stderr="device offline")
            with pytest.raises(DeviceCommandError, match="device offline"):
                provider.shell("emulator-5554", "wm", "size")


class TestRestartServer:
    def test_restart_server_calls_kill_then_start(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.return_value = _mock_subprocess()
            provider.restart_server()

        calls = [call.args[0] for call in mock_run.call_args_list]
        assert calls[0][:2] == ["adb", "kill-server"]
        assert calls[1][:2] == ["adb", "start-server"]

    def test_restart_server_tolerates_kill_server_failure(self) -> None:
        provider = AdbDeviceProvider()
        with patch("ugaf.device.adb_provider.subprocess.run") as mock_run:
            mock_run.side_effect = [
                _mock_subprocess(returncode=1, stderr="no server running"),
                _mock_subprocess(),
            ]
            provider.restart_server()  # should not raise
