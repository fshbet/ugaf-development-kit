"""Tests for ugaf.emulator.studio_locator.AndroidStudioLocator.

Regression coverage for a real ATDD acceptance-testing finding: the
original candidate list (``%LOCALAPPDATA%\\Programs\\...``,
``C:\\Program Files\\Android\\...``) never found Android Studio on this
project's actual development machine, which has it installed at
``E:\\Android\\Android Studio`` -- a sibling directory of the Android
SDK root (``E:\\Android\\SDK``), not any "well-known" default location.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ugaf.emulator.studio_locator import AndroidStudioLocator, _studio_executable_names


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("fake")


def test_finds_studio_as_sibling_of_sdk_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact real-world layout this project's own dev machine has."""
    monkeypatch.delenv("ANDROID_STUDIO_HOME", raising=False)
    sdk_root = tmp_path / "Android" / "SDK"
    sdk_root.mkdir(parents=True)
    studio_bin = tmp_path / "Android" / "Android Studio" / "bin"
    exe_name = _studio_executable_names()[0]
    _touch(studio_bin / exe_name)

    found = AndroidStudioLocator().locate(sdk_root=sdk_root)
    assert found == studio_bin / exe_name


def test_returns_none_when_not_found_anywhere(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANDROID_STUDIO_HOME", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    if sys.platform == "win32":
        monkeypatch.delenv("LOCALAPPDATA", raising=False)

    found = AndroidStudioLocator().locate(sdk_root=tmp_path / "Android" / "SDK")
    assert found is None


def test_never_raises_when_sdk_root_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANDROID_STUDIO_HOME", raising=False)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    assert AndroidStudioLocator().locate(sdk_root=None) is None


def test_android_studio_home_env_var_takes_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom_bin = tmp_path / "custom_studio" / "bin"
    exe_name = _studio_executable_names()[0]
    _touch(custom_bin / exe_name)
    monkeypatch.setenv("ANDROID_STUDIO_HOME", str(tmp_path / "custom_studio"))

    # A sibling-of-SDK-root candidate also exists, but the env var must win
    # since it is checked first.
    sdk_root = tmp_path / "Android" / "SDK"
    sdk_root.mkdir(parents=True)
    sibling_bin = tmp_path / "Android" / "Android Studio" / "bin"
    _touch(sibling_bin / exe_name)

    found = AndroidStudioLocator().locate(sdk_root=sdk_root)
    assert found == custom_bin / exe_name


def test_falls_back_to_path_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe_name = _studio_executable_names()[0]
    fake_path_binary = tmp_path / "on_path" / exe_name
    _touch(fake_path_binary)
    monkeypatch.delenv("ANDROID_STUDIO_HOME", raising=False)
    monkeypatch.setattr(
        "shutil.which", lambda name: str(fake_path_binary) if name == exe_name else None
    )

    found = AndroidStudioLocator().locate(sdk_root=None)
    assert found == fake_path_binary
