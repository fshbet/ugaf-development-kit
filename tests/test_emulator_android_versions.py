"""Tests for ugaf.emulator.android_versions.AndroidVersionManager."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ugaf.emulator.android_versions import AndroidVersionManager
from ugaf.emulator.exceptions import EmulatorCommandError, SystemImageNotAvailableError
from ugaf.emulator.sdk_locator import AndroidSdkPaths

# A trimmed but structurally faithful excerpt of real `sdkmanager --list`
# output on a Windows dev machine: the already-installed android-30
# playstore image is listed under BOTH "Installed packages" (installed=True)
# and again under "Available Packages" (installed=False) -- sdkmanager
# lists the entire catalog there, including already-installed packages.
# Regression coverage for a real bug this parser previously had: naive
# last-write-wins dict construction let the "available" (not-installed)
# duplicate silently overwrite the correct installed record.
_LIST_OUTPUT = """\
Installed packages:
  Path                                                  | Version | Description
  -------                                                | -------  | -------
  system-images;android-30;google_apis_playstore;x86_64 | 10      | Play x86_64 image

Available Packages:
  Path                                                    | Version      | Description
  -------                                                 | -------      | -------
  system-images;android-30;google_apis_playstore;x86_64   | 10           | Play x86_64 image
  system-images;android-35;google_apis_playstore;x86_64   | 6            | Play x86_64 image
  system-images;android-35;google_apis;arm64-v8a           | 3            | Google APIs ARM64 image
"""


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


@pytest.fixture
def sdk_paths(tmp_path: Path) -> AndroidSdkPaths:
    return AndroidSdkPaths(
        sdk_root=tmp_path,
        adb=tmp_path / "adb",
        emulator=tmp_path / "emulator",
        sdkmanager=tmp_path / "sdkmanager",
        avdmanager=tmp_path / "avdmanager",
        avd_home=tmp_path / "avd",
    )


def test_list_installed_dedupes_against_available_catalog_duplicate(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _mock_result(_LIST_OUTPUT))
    manager = AndroidVersionManager(sdk_paths)

    installed = manager.list_installed()
    assert len(installed) == 1
    assert installed[0].package_path == "system-images;android-30;google_apis_playstore;x86_64"
    assert installed[0].installed is True


def test_list_available_reports_full_catalog(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _mock_result(_LIST_OUTPUT))
    manager = AndroidVersionManager(sdk_paths)
    catalog = {img.package_path: img for img in manager.list_available()}
    assert len(catalog) == 3
    assert catalog["system-images;android-30;google_apis_playstore;x86_64"].installed is True
    assert catalog["system-images;android-35;google_apis_playstore;x86_64"].installed is False


def test_is_installed_true_for_installed_image(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _mock_result(_LIST_OUTPUT))
    manager = AndroidVersionManager(sdk_paths)
    assert manager.is_installed(30, "google_apis_playstore", "x86_64") is True
    assert manager.is_installed(35, "google_apis_playstore", "x86_64") is False


def test_ensure_installed_returns_immediately_when_already_installed(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        calls.append(cmd)
        return _mock_result(_LIST_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = AndroidVersionManager(sdk_paths)
    image = manager.ensure_installed(30, "google_apis_playstore", "x86_64")
    assert image.installed is True
    # Only the --list lookup should have run; no --install call.
    assert all("--install" not in cmd for cmd in calls)


def test_ensure_installed_raises_for_unknown_package(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _mock_result(_LIST_OUTPUT))
    manager = AndroidVersionManager(sdk_paths)
    with pytest.raises(SystemImageNotAvailableError):
        manager.ensure_installed(99, "google_apis_playstore", "x86_64")


_LIST_OUTPUT_AFTER_INSTALL = _LIST_OUTPUT.replace(
    "Installed packages:\n"
    "  Path                                                  | Version | Description\n"
    "  -------                                                | -------  | -------\n"
    "  system-images;android-30;google_apis_playstore;x86_64 | 10      | Play x86_64 image\n",
    "Installed packages:\n"
    "  Path                                                  | Version | Description\n"
    "  -------                                                | -------  | -------\n"
    "  system-images;android-30;google_apis_playstore;x86_64 | 10      | Play x86_64 image\n"
    "  system-images;android-35;google_apis_playstore;x86_64 | 6       | Play x86_64 image\n",
)


def test_ensure_installed_downloads_missing_image(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = {"installed": False}

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if "--install" in cmd:
            state["installed"] = True
            return _mock_result()
        return _mock_result(_LIST_OUTPUT_AFTER_INSTALL if state["installed"] else _LIST_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = AndroidVersionManager(sdk_paths)
    image = manager.ensure_installed(35, "google_apis_playstore", "x86_64")
    assert image.installed is True


def test_ensure_installed_raises_on_subprocess_failure(
    sdk_paths: AndroidSdkPaths, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        if "--install" in cmd:
            raise subprocess.TimeoutExpired(cmd, 600.0)
        return _mock_result(_LIST_OUTPUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    manager = AndroidVersionManager(sdk_paths)
    with pytest.raises(EmulatorCommandError):
        manager.ensure_installed(35, "google_apis_playstore", "x86_64")


def test_version_name_lookup(sdk_paths: AndroidSdkPaths, tmp_path: Path) -> None:
    version_file = tmp_path / "android_versions.yaml"
    version_file.write_text("versions:\n  30: Android 11\n  35: Android 15\n")
    manager = AndroidVersionManager(sdk_paths, version_names_path=version_file)
    assert manager.version_name(30) == "Android 11"
    assert manager.version_name(99) is None
