"""Tests for ugaf.emulator.dependencies.EnvironmentChecker.

Covers the ATDD acceptance requirement that every Create-Emulator
dependency (Android Studio, SDK, platform-tools, emulator.exe,
sdkmanager, avdmanager) is checked *independently* and reported with a
specific, actionable reason when missing -- never a single
all-or-nothing failure that hides which component is actually absent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ugaf.emulator.dependencies import EnvironmentChecker
from ugaf.emulator.exceptions import SdkNotFoundError
from ugaf.emulator.hardware import HardwareInfo


def _fake_hardware_detector(*, accel_available: bool = True) -> MagicMock:
    """A HardwareDetector stub reporting a usable acceleration backend by default."""
    detector = MagicMock()
    detector.detect.return_value = HardwareInfo(
        cpu_count=8,
        total_ram_mb=16384,
        accel_available=accel_available,
        accel_backend="WHPX" if accel_available else None,
        accel_message="(mocked)",
    )
    return detector


def _fake_locator(*, sdk_root: Path | None = None, missing: set[str] = frozenset()) -> MagicMock:
    locator = MagicMock()
    if sdk_root is None or "sdk" in missing:
        locator.find_sdk_root.side_effect = SdkNotFoundError("no SDK root found. Set ANDROID_HOME.")
    else:
        locator.find_sdk_root.return_value = sdk_root

    def _maybe_raise(name: str, path: Path) -> object:
        if name in missing:
            raise SdkNotFoundError(f"{name} not found. Install it via the SDK Manager.")
        return path

    if sdk_root is not None:
        # A real "cmdline-tools/latest" dir so the (non-mocked) consistency
        # check reports found -- it inspects the real filesystem, not the
        # mocked locator.
        (sdk_root / "cmdline-tools" / "latest").mkdir(parents=True, exist_ok=True)
        locator.find_adb.side_effect = lambda root: _maybe_raise("platform_tools", root / "adb")
        locator.find_emulator.side_effect = lambda root: _maybe_raise("emulator", root / "emulator")
        locator.find_sdkmanager.side_effect = lambda root: _maybe_raise(
            "sdkmanager", root / "sdkmanager"
        )
        locator.find_avdmanager.side_effect = lambda root: _maybe_raise(
            "avdmanager", root / "avdmanager"
        )
    return locator


def test_all_dependencies_found_reports_ready(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = tmp_path / "studio" / "studio64.exe"

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.ready is True
    assert report.first_missing() is None
    assert all(s.found for s in report.as_list())


def test_missing_sdk_cascades_to_every_downstream_tool(tmp_path: Path) -> None:
    locator = _fake_locator(sdk_root=None)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.ready is False
    assert report.sdk.found is False
    # Each downstream tool gets its OWN explanation, not a copy of the SDK's.
    assert "Android SDK" in report.platform_tools.detail
    assert "Android SDK" in report.emulator.detail
    assert "Android SDK" in report.sdkmanager.detail
    assert "Android SDK" in report.avdmanager.detail
    # None of the tool finders should even be called once the SDK is missing.
    locator.find_adb.assert_not_called()


def test_single_missing_tool_does_not_hide_the_others(tmp_path: Path) -> None:
    """Only avdmanager missing -- everything else must still report found."""
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root, missing={"avdmanager"})
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.ready is False
    assert report.sdk.found is True
    assert report.platform_tools.found is True
    assert report.emulator.found is True
    assert report.sdkmanager.found is True
    assert report.avdmanager.found is False
    assert "avdmanager" in report.avdmanager.detail
    first = report.first_missing()
    assert first is not None
    assert first.name == "avdmanager"


def test_android_studio_missing_is_reported_but_never_blocks(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.android_studio.found is False
    assert report.ready is True  # Studio absence is not blocking.
    assert report.first_missing() is None


def test_android_studio_found_is_reported(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_path = tmp_path / "studio" / "studio64.exe"
    studio_locator = MagicMock()
    studio_locator.locate.return_value = studio_path

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.android_studio.found is True
    assert report.android_studio.path == str(studio_path)


def test_as_list_includes_android_studio_first(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()
    names = [s.name for s in report.as_list()]
    assert names == [
        "Android Studio",
        "Android SDK",
        "Platform Tools (adb)",
        "Android Emulator (emulator.exe)",
        "sdkmanager",
        "avdmanager",
        "Command-line Tools Layout",
        "Hypervisor",
    ]


def test_cmdline_tools_consistency_found_with_latest_dir(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.cmdline_tools_consistency.found is True


def test_cmdline_tools_consistency_flags_ambiguous_multi_version_layout(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    (sdk_root / "cmdline-tools" / "latest").rmdir()
    (sdk_root / "cmdline-tools" / "9.0").mkdir(parents=True)
    (sdk_root / "cmdline-tools" / "12.0").mkdir(parents=True)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(locator, studio_locator, _fake_hardware_detector()).check()

    assert report.cmdline_tools_consistency.found is False
    assert "9.0" in report.cmdline_tools_consistency.detail
    assert "12.0" in report.cmdline_tools_consistency.detail
    # Not blocking -- overall readiness is unaffected.
    assert report.ready is True


def test_hypervisor_unavailable_is_reported_but_not_blocking(tmp_path: Path) -> None:
    sdk_root = tmp_path / "sdk"
    locator = _fake_locator(sdk_root=sdk_root)
    studio_locator = MagicMock()
    studio_locator.locate.return_value = None

    report = EnvironmentChecker(
        locator, studio_locator, _fake_hardware_detector(accel_available=False)
    ).check()

    assert report.hypervisor.found is False
    assert report.ready is True
