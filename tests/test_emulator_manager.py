"""Tests for ugaf.emulator.manager.EmulatorManager (the facade)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ugaf.emulator.manager import EmulatorManager
from ugaf.emulator.performance import PerformanceProfileManager
from ugaf.emulator.profiles import DeviceProfileManager
from ugaf.emulator.provider import EmulatorProvider, emulator_registry
from ugaf.emulator.sdk_locator import AndroidSdkPaths
from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle


class _FakeProvider(EmulatorProvider):
    """Minimal in-memory fake provider used to isolate EmulatorManager from any real SDK tool."""

    def __init__(self, sdk_paths, android_versions, logger=None, first_console_port=5554):  # noqa: ANN001
        self.sdk_paths = sdk_paths
        self.avds: dict[str, AvdInfo] = {}
        self.running: set[str] = set()

    def list(self):  # noqa: ANN201
        return list(self.avds.values())

    def create(self, name, device_profile, performance_profile, force=False):  # noqa: ANN001, ANN201
        info = AvdInfo(
            name=name,
            device=device_profile.hardware_name,
            target=None,
            abi=device_profile.abi,
            path="x",
            valid=True,
        )
        self.avds[name] = info
        return info

    def delete(self, name):  # noqa: ANN001
        self.avds.pop(name, None)
        self.running.discard(name)

    def rename(self, name, new_name):  # noqa: ANN001
        import dataclasses

        self.avds[new_name] = dataclasses.replace(self.avds.pop(name), name=new_name)

    def clone(self, source, target):  # noqa: ANN001, ANN201
        info = self.avds[source]
        cloned = AvdInfo(
            name=target, device=info.device, target=info.target, abi=info.abi, path="y", valid=True
        )
        self.avds[target] = cloned
        return cloned

    def update_hardware(self, name, performance_profile):  # noqa: ANN001
        pass

    def start(self, name):  # noqa: ANN001, ANN201
        self.running.add(name)
        return EmulatorInstanceHandle(
            name=name,
            adb_serial="emulator-5554",
            console_port=5554,
            adb_port=5555,
            pid=1234,
            log_path="log",
            working_directory="wd",
        )

    def stop(self, name):  # noqa: ANN001
        self.running.discard(name)

    def is_running(self, name):  # noqa: ANN001, ANN201
        return name in self.running

    def detect_crash(self, name):  # noqa: ANN001, ANN201
        return False

    def wait_until_booted(self, name, timeout):  # noqa: ANN001, ANN201
        return name in self.running

    def install_apk(self, name, apk_path):  # noqa: ANN001
        pass

    def push(self, name, source, destination):  # noqa: ANN001
        pass

    def pull(self, name, source, destination):  # noqa: ANN001
        pass


@pytest.fixture(autouse=True)
def fake_provider_registered():
    if not emulator_registry.is_registered("fake"):
        emulator_registry.register("fake", _FakeProvider)
    yield
    emulator_registry.unregister("fake")


@pytest.fixture
def manufacturers_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "manufacturers.yaml"
    path.write_text(
        """
manufacturers:
  Google:
    devices:
      pixel_6:
        brand: Google
        model: Pixel 6
        device_name: pixel_6
        hardware_name: pixel_6
        android_version: "Android 15"
        api_level: 35
        resolution: [1080, 2400]
        dpi: 411
        ram_mb: 4096
        cpu_count: 4
        storage_mb: 8192
        abi: x86_64
"""
    )
    return path


@pytest.fixture
def performance_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "performance_profiles.yaml"
    path.write_text(
        """
profiles:
  mid_range:
    cpu_count: 4
    ram_mb: 4096
"""
    )
    return path


@pytest.fixture
def manager(
    tmp_path: Path,
    manufacturers_yaml: Path,
    performance_yaml: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> EmulatorManager:
    def fake_locate(self, sdk_root_override=None):  # noqa: ANN001, ANN202
        return AndroidSdkPaths(
            sdk_root=tmp_path,
            adb=tmp_path / "adb",
            emulator=tmp_path / "emulator",
            sdkmanager=tmp_path / "sdkmanager",
            avdmanager=tmp_path / "avdmanager",
            avd_home=tmp_path / "avd",
        )

    monkeypatch.setattr("ugaf.emulator.manager.AndroidSdkLocator.locate", fake_locate)
    monkeypatch.setattr(
        "ugaf.emulator.manager.AndroidVersionManager",
        lambda *a, **k: MagicMock(),
    )

    return EmulatorManager(
        provider_name="fake",
        device_profiles=DeviceProfileManager(manufacturers_yaml),
        performance_profiles=PerformanceProfileManager(performance_yaml),
    )


def test_create_start_boot_stop_delete_lifecycle(manager: EmulatorManager) -> None:
    avd = manager.create("MyAvd", "Google", "pixel_6", "mid_range")
    assert avd.name == "MyAvd"
    assert manager.is_running("MyAvd") is False

    handle = manager.start("MyAvd")
    assert handle.adb_serial == "emulator-5554"
    assert manager.is_running("MyAvd") is True

    assert manager.wait_until_booted("MyAvd", timeout=5) is True
    assert manager.detect_crash("MyAvd") is False

    manager.stop("MyAvd")
    assert manager.is_running("MyAvd") is False

    manager.delete("MyAvd")
    assert manager.list() == []


def test_create_uses_device_and_performance_profiles(manager: EmulatorManager) -> None:
    manager.create("Another", "Google", "pixel_6", "mid_range")
    devices = manager.list_devices("Google")
    assert devices[0].device_name == "pixel_6"
    assert "mid_range" in manager.list_performance_profiles()


def test_list_manufacturers(manager: EmulatorManager) -> None:
    assert manager.list_manufacturers() == ["Google"]


def test_clone_and_rename(manager: EmulatorManager) -> None:
    manager.create("Base", "Google", "pixel_6", "mid_range")
    cloned = manager.clone("Base", "Clone")
    assert cloned.name == "Clone"
    manager.rename("Clone", "Renamed")
    names = {a.name for a in manager.list()}
    assert "Renamed" in names
    assert "Clone" not in names
