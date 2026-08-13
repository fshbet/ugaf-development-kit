"""Tests for ugaf.android_platform.manager.AndroidPlatformManager.

The facade wraps already-constructed EmulatorManager/DeviceManager/
EnvironmentChecker instances (never builds its own SDK-locating
EmulatorManager) so these tests use plain mocks/fakes -- no real
Android SDK required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ugaf.android_platform.manager import AndroidPlatformManager
from ugaf.device.lifecycle import DeviceLifecycle, DeviceState
from ugaf.device.manager import DeviceManager
from ugaf.emulator.dependencies import DependencyReport, DependencyStatus
from ugaf.emulator.exceptions import EmulatorManagerError
from ugaf.emulator.hardware import HardwareInfo
from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus


def _ok(name: str) -> DependencyStatus:
    return DependencyStatus(name, True, f"/fake/{name}", "")


def _ready_report() -> DependencyReport:
    return DependencyReport(
        android_studio=DependencyStatus("Android Studio", False, None, ""),
        sdk=_ok("sdk"),
        platform_tools=_ok("platform_tools"),
        emulator=_ok("emulator"),
        sdkmanager=_ok("sdkmanager"),
        avdmanager=_ok("avdmanager"),
        cmdline_tools_consistency=_ok("cmdline_tools"),
        hypervisor=_ok("hypervisor"),
    )


def _not_ready_report() -> DependencyReport:
    missing = DependencyStatus("avdmanager", False, None, "avdmanager not found. Install it.")
    report = _ready_report()
    return DependencyReport(
        android_studio=report.android_studio,
        sdk=report.sdk,
        platform_tools=report.platform_tools,
        emulator=report.emulator,
        sdkmanager=report.sdkmanager,
        avdmanager=missing,
        cmdline_tools_consistency=report.cmdline_tools_consistency,
        hypervisor=report.hypervisor,
    )


class _FakeProvider(DeviceProvider):
    def __init__(self, devices: list[DeviceInfo]) -> None:
        self._devices = devices

    def list_devices(self) -> list[DeviceInfo]:
        return self._devices

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return next((d for d in self._devices if d.id == device_id), None)


def _device_manager(devices: list[DeviceInfo]) -> DeviceManager:
    dm = DeviceManager()
    dm.register_provider("fake", _FakeProvider(devices))
    return dm


def _emulator_manager(sdk_root: Path = Path("/fake/sdk")) -> MagicMock:
    manager = MagicMock()
    manager.sdk_paths.sdk_root = sdk_root
    manager.detect_hardware.return_value = HardwareInfo(
        cpu_count=8,
        total_ram_mb=16384,
        accel_available=True,
        accel_backend="WHPX",
        accel_message="",
    )
    return manager


def _checker(report: DependencyReport) -> MagicMock:
    checker = MagicMock()
    checker.check.return_value = report
    return checker


def test_start_virtual_device_validates_before_launching() -> None:
    emulator_manager = _emulator_manager()
    emulator_manager.start.return_value = EmulatorInstanceHandle(
        name="MyAvd",
        adb_serial="emulator-5554",
        console_port=5554,
        adb_port=5555,
        pid=1234,
        log_path="log",
        working_directory="wd",
    )
    lifecycle = DeviceLifecycle()
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), lifecycle, _checker(_ready_report())
    )

    handle = platform.start_virtual_device("MyAvd")

    assert handle.adb_serial == "emulator-5554"
    emulator_manager.start.assert_called_once_with("MyAvd")
    # The name-keyed entry is forgotten once launched -- adb_serial becomes canonical.
    assert lifecycle.get("MyAvd").state is DeviceState.DISCONNECTED


def test_start_virtual_device_refuses_when_dependency_missing() -> None:
    emulator_manager = _emulator_manager()
    lifecycle = DeviceLifecycle()
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), lifecycle, _checker(_not_ready_report())
    )

    with pytest.raises(EmulatorManagerError, match="avdmanager"):
        platform.start_virtual_device("MyAvd")

    emulator_manager.start.assert_not_called()
    assert lifecycle.get("MyAvd").state is DeviceState.ERROR


def test_stop_virtual_device_transitions_through_stopping_to_stopped() -> None:
    emulator_manager = _emulator_manager()
    lifecycle = DeviceLifecycle()
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), lifecycle, _checker(_ready_report())
    )

    platform.stop_virtual_device("MyAvd")

    emulator_manager.stop.assert_called_once_with("MyAvd")
    assert lifecycle.get("MyAvd").state is DeviceState.STOPPED


def test_stop_virtual_device_transitions_to_error_on_failure() -> None:
    emulator_manager = _emulator_manager()
    emulator_manager.stop.side_effect = RuntimeError("adb emu kill failed")
    lifecycle = DeviceLifecycle()
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), lifecycle, _checker(_ready_report())
    )

    with pytest.raises(RuntimeError):
        platform.stop_virtual_device("MyAvd")

    assert lifecycle.get("MyAvd").state is DeviceState.ERROR


def test_list_physical_devices_excludes_emulator_serials() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        ),
        DeviceInfo(
            id="ABC123XYZ",
            name="Pixel",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        ),
    ]
    platform = AndroidPlatformManager(
        _emulator_manager(), _device_manager(devices), DeviceLifecycle(), _checker(_ready_report())
    )

    physical = platform.list_physical_devices()

    assert [d.id for d in physical] == ["ABC123XYZ"]


def test_platform_health_reports_overall_healthy_from_dependencies() -> None:
    emulator_manager = _emulator_manager()
    emulator_manager.list.return_value = [
        AvdInfo(name="A", device=None, target=None, abi=None, path="p", valid=True, running=True),
    ]
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), DeviceLifecycle(), _checker(_ready_report())
    )

    health = platform.platform_health()

    assert health.overall_healthy is True
    assert health.virtual_device_count == 1
    assert health.physical_device_count == 0


def test_create_virtual_device_delegates_to_emulator_manager() -> None:
    emulator_manager = _emulator_manager()
    emulator_manager.create.return_value = AvdInfo(
        name="ROG_A15",
        device="rog_phone_9",
        target=None,
        abi="x86_64",
        path="p",
        valid=True,
        display_name="ROG A15",
    )
    platform = AndroidPlatformManager(
        emulator_manager, _device_manager([]), DeviceLifecycle(), _checker(_ready_report())
    )

    avd = platform.create_virtual_device("ROG A15", "Asus", "rog_phone_9", "gaming")

    assert avd.name == "ROG_A15"
    assert avd.display_name == "ROG A15"
    emulator_manager.create.assert_called_once_with("ROG A15", "Asus", "rog_phone_9", "gaming")
