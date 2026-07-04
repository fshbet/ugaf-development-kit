"""Tests for ugaf.emulator.sdk_locator.AndroidSdkLocator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ugaf.emulator.exceptions import SdkNotFoundError
from ugaf.emulator.sdk_locator import AndroidSdkLocator, _exe


def _make_fake_sdk(root: Path, *, cmdline_tools_dir: str = "latest") -> None:
    """Build a minimal fake Android SDK layout under *root*."""
    (root / "platform-tools").mkdir(parents=True)
    (root / "platform-tools" / _exe("adb")).write_text("fake adb")
    (root / "emulator").mkdir()
    (root / "emulator" / _exe("emulator")).write_text("fake emulator")
    tools_bin = root / "cmdline-tools" / cmdline_tools_dir / "bin"
    tools_bin.mkdir(parents=True)
    suffix = ".bat" if sys.platform == "win32" else ""
    (tools_bin / f"sdkmanager{suffix}").write_text("fake sdkmanager")
    (tools_bin / f"avdmanager{suffix}").write_text("fake avdmanager")


def test_locate_with_explicit_override(tmp_path: Path) -> None:
    _make_fake_sdk(tmp_path)
    paths = AndroidSdkLocator().locate(sdk_root_override=tmp_path)
    assert paths.sdk_root == tmp_path
    assert paths.adb.is_file()
    assert paths.emulator.is_file()
    assert paths.sdkmanager.is_file()
    assert paths.avdmanager.is_file()


def test_locate_prefers_sdk_platform_tools_adb_over_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SDK's own platform-tools `adb` must win over whatever `adb` is first on PATH."""
    _make_fake_sdk(tmp_path)
    monkeypatch.setattr("shutil.which", lambda _name: r"C:\Program Files\Adb\adb.exe")
    paths = AndroidSdkLocator().locate(sdk_root_override=tmp_path)
    assert paths.adb == tmp_path / "platform-tools" / _exe("adb")


def test_locate_prefers_latest_cmdline_tools_dir(tmp_path: Path) -> None:
    _make_fake_sdk(tmp_path, cmdline_tools_dir="12.0")
    # Add a "latest" dir too -- it must win over the versioned one.
    suffix = ".bat" if sys.platform == "win32" else ""
    latest_bin = tmp_path / "cmdline-tools" / "latest" / "bin"
    latest_bin.mkdir(parents=True)
    (latest_bin / f"sdkmanager{suffix}").write_text("latest sdkmanager")
    (latest_bin / f"avdmanager{suffix}").write_text("latest avdmanager")

    paths = AndroidSdkLocator().locate(sdk_root_override=tmp_path)
    assert paths.sdkmanager == latest_bin / f"sdkmanager{suffix}"


def test_locate_falls_back_to_highest_versioned_cmdline_tools_dir(tmp_path: Path) -> None:
    _make_fake_sdk(tmp_path, cmdline_tools_dir="9.0")
    suffix = ".bat" if sys.platform == "win32" else ""
    newer_bin = tmp_path / "cmdline-tools" / "12.0" / "bin"
    newer_bin.mkdir(parents=True)
    (newer_bin / f"sdkmanager{suffix}").write_text("newer sdkmanager")
    (newer_bin / f"avdmanager{suffix}").write_text("newer avdmanager")

    paths = AndroidSdkLocator().locate(sdk_root_override=tmp_path)
    assert paths.sdkmanager == newer_bin / f"sdkmanager{suffix}"


def test_locate_raises_when_no_sdk_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    with pytest.raises(SdkNotFoundError):
        AndroidSdkLocator().locate(sdk_root_override=tmp_path / "does_not_exist")


def test_locate_raises_when_emulator_missing(tmp_path: Path) -> None:
    (tmp_path / "platform-tools").mkdir(parents=True)
    (tmp_path / "platform-tools" / _exe("adb")).write_text("fake adb")
    with pytest.raises(SdkNotFoundError, match="emulator"):
        AndroidSdkLocator().locate(sdk_root_override=tmp_path)


def test_locate_uses_android_home_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _make_fake_sdk(tmp_path)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path))
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    paths = AndroidSdkLocator().locate()
    assert paths.sdk_root == tmp_path


def test_avd_home_defaults_to_dot_android_avd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANDROID_AVD_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    locator = AndroidSdkLocator()
    assert locator._find_avd_home() == tmp_path / ".android" / "avd"


def test_avd_home_respects_android_avd_home_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom_avds"
    monkeypatch.setenv("ANDROID_AVD_HOME", str(custom))
    locator = AndroidSdkLocator()
    assert locator._find_avd_home() == custom
