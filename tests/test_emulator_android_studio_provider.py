"""Tests for ugaf.emulator.providers.android_studio.AndroidStudioProvider.

All ``avdmanager``/``emulator``/``adb`` subprocess invocations are
mocked at ``ugaf.emulator.providers.android_studio.subprocess.run`` (or
``.Popen`` for the long-running ``emulator`` process) — no real SDK
tooling required. Where a real ``avdmanager`` command would touch the
filesystem (``create``, and this provider's own rename/clone/hardware-
update logic), the fake subprocess side effects create the same real
files under ``tmp_path`` so the provider's *own* file-handling code
(never mocked) is exercised for real.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ugaf.emulator._avd_config import read_avd_config, write_avd_config
from ugaf.emulator.exceptions import (
    AvdAlreadyExistsError,
    AvdNotFoundError,
    EmulatorCommandError,
)
from ugaf.emulator.providers.android_studio import AndroidStudioProvider
from ugaf.emulator.sdk_locator import AndroidSdkPaths
from ugaf.emulator.types import DeviceProfile, PerformanceProfile, SystemImageInfo

_AVD_LIST_OUTPUT = """\
Available Android Virtual Devices:
    Name: PixelPlay
  Device: pixel_6_pro (Google)
    Path: {avd_home}\\PixelPlay.avd
  Target: Google Play (Google Inc.)
          Based on: Android 11.0 ("R") Tag/ABI: google_apis_playstore/x86_64
  Sdcard: 512 MB

The following Android Virtual Devices could not be loaded:
    Name: TestDevice
    Path: {avd_home}\\TestDevice.avd
   Error: Missing system image for Google APIs x86_64 TestDevice.
"""


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


@pytest.fixture
def sdk_paths(tmp_path: Path) -> AndroidSdkPaths:
    avd_home = tmp_path / "avd"
    avd_home.mkdir()
    return AndroidSdkPaths(
        sdk_root=tmp_path,
        adb=tmp_path / "adb",
        emulator=tmp_path / "emulator",
        sdkmanager=tmp_path / "sdkmanager",
        avdmanager=tmp_path / "avdmanager",
        avd_home=avd_home,
    )


@pytest.fixture
def android_versions(sdk_paths: AndroidSdkPaths) -> MagicMock:
    mock = MagicMock()
    mock.ensure_installed.return_value = SystemImageInfo(
        api_level=30,
        version_name="Android 11",
        tag="google_apis_playstore",
        abi="x86_64",
        installed=True,
        package_path="system-images;android-30;google_apis_playstore;x86_64",
    )
    return mock


@pytest.fixture
def device_profile() -> DeviceProfile:
    return DeviceProfile(
        manufacturer="Google",
        brand="Google",
        model="Pixel 6 Pro",
        device_name="pixel_6_pro",
        hardware_name="pixel_6_pro",
        android_version="Android 11",
        api_level=30,
        resolution=(1440, 3120),
        dpi=512,
        ram_mb=4096,
        cpu_count=4,
        storage_mb=8192,
        abi="x86_64",
        gpu_mode="auto",
        play_store=True,
        snapshot_support=True,
    )


@pytest.fixture
def performance_profile() -> PerformanceProfile:
    return PerformanceProfile(
        name="mid_range",
        cpu_count=4,
        ram_mb=4096,
        heap_mb=256,
        storage_mb=8192,
        gpu_mode="auto",
        network_speed="full",
        snapshot_enabled=True,
    )


def _write_fake_avd(avd_home: Path, name: str, config: dict[str, str] | None = None) -> None:
    avd_dir = avd_home / f"{name}.avd"
    avd_dir.mkdir(parents=True, exist_ok=True)
    write_avd_config(
        avd_dir / "config.ini",
        config
        or {
            "avd.id": name,
            "avd.name": name,
            "hw.cpu.ncore": "2",
            "hw.ramSize": "2048",
            "abi.type": "x86_64",
        },
    )
    write_avd_config(
        avd_home / f"{name}.ini",
        {
            "avd.ini.encoding": "UTF-8",
            "path": str(avd_dir),
            "path.rel": f"avd\\{name}.avd",
            "target": "android-30",
        },
    )


def test_list_parses_valid_and_broken_avds(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "list" in cmd and "avd" in cmd:
            return _mock_result(_AVD_LIST_OUTPUT.format(avd_home=sdk_paths.avd_home))
        if "devices" in cmd:
            return _mock_result("List of devices attached\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    avds = provider.list()
    by_name = {a.name: a for a in avds}
    assert by_name["PixelPlay"].valid is True
    assert by_name["PixelPlay"].abi == "x86_64"
    assert by_name["TestDevice"].valid is False
    assert "Missing system image" in by_name["TestDevice"].error


def test_create_ensures_system_image_and_applies_profiles(
    sdk_paths: AndroidSdkPaths,
    android_versions: MagicMock,
    device_profile: DeviceProfile,
    performance_profile: PerformanceProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"created": False}

    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "create" in cmd and "avd" in cmd:
            _write_fake_avd(sdk_paths.avd_home, "NewAvd")
            state["created"] = True
            return _mock_result()
        if "list" in cmd and "avd" in cmd:
            if state["created"]:
                return _mock_result(
                    "Available Android Virtual Devices:\n    Name: NewAvd\n    Path: x\n"
                )
            return _mock_result("Available Android Virtual Devices:\n")
        if "devices" in cmd:
            return _mock_result("List of devices attached\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    avd = provider.create("NewAvd", device_profile, performance_profile)

    android_versions.ensure_installed.assert_called_once_with(
        30, tag="google_apis_playstore", abi="x86_64"
    )
    assert avd.name == "NewAvd"

    config = read_avd_config(sdk_paths.avd_home / "NewAvd.avd" / "config.ini")
    assert config["hw.cpu.ncore"] == "4"
    assert config["hw.ramSize"] == "4096"
    assert config["hw.lcd.width"] == "1440"
    assert config["hw.lcd.height"] == "3120"


def test_create_raises_when_avd_already_exists(
    sdk_paths: AndroidSdkPaths,
    android_versions: MagicMock,
    device_profile: DeviceProfile,
    performance_profile: PerformanceProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "list" in cmd and "avd" in cmd:
            return _mock_result(_AVD_LIST_OUTPUT.format(avd_home=sdk_paths.avd_home))
        if "devices" in cmd:
            return _mock_result("List of devices attached\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(AvdAlreadyExistsError):
        provider.create("PixelPlay", device_profile, performance_profile)


def test_update_hardware_rewrites_config(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, performance_profile: PerformanceProfile
) -> None:
    _write_fake_avd(sdk_paths.avd_home, "Existing")
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    provider.update_hardware("Existing", performance_profile)

    config = read_avd_config(sdk_paths.avd_home / "Existing.avd" / "config.ini")
    assert config["hw.cpu.ncore"] == "4"
    assert config["vm.heapSize"] == "256"
    assert config["fastboot.forceColdBoot"] == "no"


def test_update_hardware_raises_for_unknown_avd(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, performance_profile: PerformanceProfile
) -> None:
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(AvdNotFoundError):
        provider.update_hardware("NoSuchAvd", performance_profile)


def test_rename_moves_directory_and_rewrites_identity(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock
) -> None:
    _write_fake_avd(sdk_paths.avd_home, "Old")
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    provider.rename("Old", "New")

    assert not (sdk_paths.avd_home / "Old.avd").exists()
    assert (sdk_paths.avd_home / "New.avd").is_dir()
    config = read_avd_config(sdk_paths.avd_home / "New.avd" / "config.ini")
    assert config["avd.id"] == "New"
    ini = read_avd_config(sdk_paths.avd_home / "New.ini")
    assert ini["path"] == str(sdk_paths.avd_home / "New.avd")


def test_rename_raises_when_source_missing(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock
) -> None:
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(AvdNotFoundError):
        provider.rename("Ghost", "New")


def test_rename_raises_when_target_exists(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock
) -> None:
    _write_fake_avd(sdk_paths.avd_home, "Old")
    _write_fake_avd(sdk_paths.avd_home, "New")
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(AvdAlreadyExistsError):
        provider.rename("Old", "New")


def test_clone_copies_directory_and_keeps_source(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "list" in cmd and "avd" in cmd:
            return _mock_result(
                "Available Android Virtual Devices:\n    Name: Target\n    Path: x\n"
            )
        if "devices" in cmd:
            return _mock_result("List of devices attached\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    _write_fake_avd(sdk_paths.avd_home, "Source")
    provider = AndroidStudioProvider(sdk_paths, android_versions)

    target_dir = sdk_paths.avd_home / "Target.avd"
    result = provider.clone("Source", "Target")

    assert (sdk_paths.avd_home / "Source.avd").exists()
    assert target_dir.is_dir()
    config = read_avd_config(target_dir / "config.ini")
    assert config["avd.id"] == "Target"
    assert result.name == "Target"


def test_delete_stops_running_instance_first(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        calls.append(cmd)
        if "list" in cmd and "avd" in cmd:
            return _mock_result(
                "Available Android Virtual Devices:\n    Name: RunningAvd\n    Path: x\n"
            )
        if "devices" in cmd:
            return _mock_result("List of devices attached\nemulator-5554\tdevice\n")
        if "emu" in cmd and "name" in cmd:
            return _mock_result("RunningAvd\nOK\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    provider.delete("RunningAvd")

    assert any("kill" in c for c in calls)
    assert any("delete" in c for c in calls)


def test_is_running_false_when_no_matching_serial(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "devices" in cmd:
            return _mock_result("List of devices attached\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    assert provider.is_running("Anything") is False


def test_is_running_true_when_serial_matches(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list, **kwargs: object) -> MagicMock:
        if "devices" in cmd:
            return _mock_result("List of devices attached\nemulator-5554\tdevice\n")
        if "emu" in cmd and "name" in cmd:
            return _mock_result("PixelPlay\nOK\n")
        return _mock_result()

    monkeypatch.setattr(subprocess, "run", fake_run)
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    assert provider.is_running("PixelPlay") is True


def test_install_apk_raises_when_not_running(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: _mock_result("List of devices attached\n")
    )
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(EmulatorCommandError):
        provider.install_apk("NotRunning", "app.apk")


def test_wait_until_booted_returns_false_when_not_running(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: _mock_result("List of devices attached\n")
    )
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    assert provider.wait_until_booted("NotRunning", timeout=0.1) is False


def test_tool_failure_raises_emulator_command_error(
    sdk_paths: AndroidSdkPaths, android_versions: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        subprocess, "run", lambda cmd, **k: _mock_result(returncode=1, stderr="boom")
    )
    provider = AndroidStudioProvider(sdk_paths, android_versions)
    with pytest.raises(EmulatorCommandError):
        provider.list()
