"""Tests for ugaf.emulator.boot_diagnostics.BootMonitor (ADR-023).

Covers the root-cause requirement that a boot that doesn't complete is
reported as the *exact* stage that got stuck (emulator process, ADB
visibility, boot-completion properties, boot animation, or launcher) --
never a generic "did not finish booting" with no further explanation.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import MagicMock

from ugaf.device.manager import DeviceManager
from ugaf.emulator.boot_diagnostics import BootMonitor
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus


# A real DeviceProvider subclass, not a bare MagicMock: as of Python 3.12,
# runtime_checkable Protocol isinstance checks use inspect.getattr_static,
# which bypasses MagicMock's dynamic __getattr__ attribute creation -- a
# plain MagicMock() fails the `_ShellCapableTransport` isinstance check
# DeviceManager.shell_sync() relies on, even though hasattr(mock, "shell")
# is True.
class _FakeProvider(DeviceProvider):
    def __init__(
        self, devices: list[DeviceInfo], shell_fn: Callable[..., str] | None = None
    ) -> None:
        self._devices = devices
        self._shell_fn = shell_fn

    def list_devices(self) -> list[DeviceInfo]:
        return self._devices

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return next((d for d in self._devices if d.id == device_id), None)

    def shell(self, device_id: str, *args: str) -> str:
        if self._shell_fn is None:
            raise AssertionError("shell() called without a shell_fn configured")
        return self._shell_fn(device_id, *args)


def _device_manager(
    devices: list[DeviceInfo], shell_side_effect: Callable[..., str] | None = None
) -> DeviceManager:
    dm = DeviceManager()
    dm.register_provider("fake", _FakeProvider(devices, shell_side_effect))
    return dm


def _emulator_manager(is_running: bool) -> MagicMock:
    manager = MagicMock()
    manager.is_running.return_value = is_running
    return manager


def test_reports_emulator_process_stage_when_process_not_running() -> None:
    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager([]),
        _emulator_manager(is_running=False),
        "MyAvd",
        "emulator-5554",
        timeout=5,
    )
    assert diagnostics.failed_stage == "emulator_process"
    assert diagnostics.emulator_process_running is False
    assert "crashed" in diagnostics.recommended_action or "log" in diagnostics.recommended_action


def test_reports_adb_visibility_stage_when_device_never_appears() -> None:
    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager([]),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=0.1,
    )
    assert diagnostics.failed_stage == "adb_visibility"
    assert diagnostics.emulator_process_running is True
    assert diagnostics.adb_visible is False


def test_reports_adb_offline_status_distinct_from_not_visible() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.OFFLINE,
            platform="android",
            transport="adb",
        )
    ]
    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager(devices),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=0.1,
    )
    assert diagnostics.failed_stage == "adb_visibility"
    assert diagnostics.adb_visible is True
    assert diagnostics.adb_status == "offline"


def test_reports_boot_completed_stage_when_property_never_flips() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        )
    ]

    def shell(device_id: str, *args: str) -> str:
        return "0\n"  # sys.boot_completed / dev.bootcomplete never reach 1

    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager(devices, shell),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=0.1,
    )
    assert diagnostics.failed_stage == "boot_completed"
    assert diagnostics.boot_completed is False
    assert diagnostics.dev_bootcomplete is False


def test_reports_bootanim_stage_when_boot_completed_but_animation_still_running() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        )
    ]

    def shell(device_id: str, *args: str) -> str:
        if "bootanim" in args:
            return "running\n"
        if "boot_completed" in " ".join(args) or "dev.bootcomplete" in args:
            return "1\n"
        return ""

    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager(devices, shell),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=0.1,
    )
    assert diagnostics.failed_stage == "bootanim"
    assert diagnostics.boot_completed is True
    assert diagnostics.bootanim_stopped is False


def test_reports_launcher_stage_when_no_foreground_package_found() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        )
    ]

    def shell(device_id: str, *args: str) -> str:
        if "dumpsys" in args:
            return "mCurrentFocus=null\n"
        if any("bootanim" in a for a in args):
            return "stopped\n"
        return "1\n"

    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager(devices, shell),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=0.1,
    )
    assert diagnostics.failed_stage == "launcher"
    assert diagnostics.bootanim_stopped is True
    assert diagnostics.foreground_package is None


def test_reports_no_failed_stage_when_fully_booted() -> None:
    devices = [
        DeviceInfo(
            id="emulator-5554",
            name="AVD",
            status=DeviceStatus.ONLINE,
            platform="android",
            transport="adb",
        )
    ]

    def shell(device_id: str, *args: str) -> str:
        if "dumpsys" in args:
            return "mCurrentFocus=Window{... com.android.launcher3/.Launcher}\n"
        if any("bootanim" in a for a in args):
            return "stopped\n"
        return "1\n"

    monitor = BootMonitor(poll_interval=0.01)
    diagnostics = monitor.wait_for_boot(
        _device_manager(devices, shell),
        _emulator_manager(is_running=True),
        "MyAvd",
        "emulator-5554",
        timeout=5,
    )
    assert diagnostics.failed_stage is None
    assert diagnostics.foreground_package == "com.android.launcher3"
    assert diagnostics.recommended_action is None
