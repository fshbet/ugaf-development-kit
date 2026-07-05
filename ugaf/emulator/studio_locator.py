r"""Locates a local Android Studio installation, if any.

Android Studio itself is **not** required to create or run AVDs --
``avdmanager``/``emulator``/``sdkmanager`` are plain command-line tools
that work headlessly. This locator exists only so the "Open Android
Studio" convenience button (and the environment/dependency status
panel) can report accurately whether the IDE is actually installed,
rather than guessing.

No path is hardcoded as the *only* option: a real audit of this
project's development machine found Android Studio installed at
``E:\\Android\\Android Studio`` -- a sibling directory of the Android
SDK root (``E:\\Android\\SDK``), not any of the "well-known" default
install locations (``%LOCALAPPDATA%\\Programs\\...``,
``C:\\Program Files\\Android\\...``) that earlier code only checked.
That sibling-of-the-SDK-root layout is common enough (both installed
under one parent folder) that it's checked explicitly, ahead of the
generic per-OS defaults.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

__all__ = [
    "AndroidStudioLocator",
]


def _studio_executable_names() -> tuple[str, ...]:
    """Return candidate Android Studio launcher filenames for this OS."""
    if sys.platform == "win32":
        return ("studio64.exe", "studio.exe", "studio.bat")
    if sys.platform == "darwin":
        return ("studio",)
    return ("studio.sh", "studio")


class AndroidStudioLocator:
    """Finds a local Android Studio installation."""

    def locate(self, sdk_root: Path | None = None) -> Path | None:
        """Search for an Android Studio launcher, returning its path if found.

        Args:
            sdk_root: The resolved Android SDK root, if known -- used to
                check the common "SDK and Studio installed as siblings
                under one parent folder" layout.

        Returns:
            Path to the Android Studio launcher executable, or ``None``
            if it could not be found anywhere checked. Never raises --
            Android Studio is optional, so a caller decides what a
            "not found" result means for it.

        """
        for directory in self._candidate_directories(sdk_root):
            for name in _studio_executable_names():
                candidate = directory / name
                if candidate.is_file():
                    return candidate

        for name in _studio_executable_names():
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    def _candidate_directories(self, sdk_root: Path | None) -> list[Path]:
        directories: list[Path] = []
        studio_home = os.environ.get("ANDROID_STUDIO_HOME")
        if studio_home:
            directories.append(Path(studio_home) / "bin")
        if sdk_root is not None:
            directories.append(sdk_root.parent / "Android Studio" / "bin")
        directories.extend(self._default_install_dirs())
        return directories

    def _default_install_dirs(self) -> list[Path]:
        """Well-known per-OS default Android Studio install locations."""
        home = Path.home()
        if sys.platform == "win32":
            directories: list[Path] = []
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                directories.append(Path(local_app_data) / "Programs" / "Android Studio" / "bin")
            directories.append(Path(r"C:\Program Files\Android\Android Studio\bin"))
            directories.append(Path(r"C:\Program Files (x86)\Android\Android Studio\bin"))
            return directories
        if sys.platform == "darwin":
            return [Path("/Applications/Android Studio.app/Contents/MacOS")]
        return [Path("/opt/android-studio/bin"), home / "android-studio" / "bin"]
