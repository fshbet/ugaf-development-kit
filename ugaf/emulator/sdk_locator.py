r"""Locates a local Android SDK installation and its command-line tools.

No SDK path is ever hardcoded. Resolution order for the SDK root:

1. An explicit path passed to :meth:`AndroidSdkLocator.locate`.
2. The ``ANDROID_HOME`` environment variable.
3. The ``ANDROID_SDK_ROOT`` environment variable (older, still widely set).
4. Well-known per-OS default install locations (Android Studio's default).

Within the SDK root, ``adb`` is preferred from ``platform-tools/`` under
that root rather than trusting whatever ``adb`` happens to be first on
``PATH`` -- a real environment audit of this project's development
machine found *two* installed copies of ``adb.exe`` (one under the SDK,
one under ``C:\Program Files\Adb``), which would silently pick the
wrong tooling version if resolution were PATH-first.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from ugaf.emulator.exceptions import SdkNotFoundError

__all__ = [
    "AndroidSdkPaths",
    "AndroidSdkLocator",
]


def _exe(name: str) -> str:
    """Append the platform executable suffix to a tool base name."""
    return f"{name}.exe" if sys.platform == "win32" else name


def _bat_or_exe(name: str) -> tuple[str, ...]:
    """Return candidate filenames for a command-line-tools script (``.bat`` on Windows)."""
    if sys.platform == "win32":
        return (f"{name}.bat", f"{name}.exe")
    return (name,)


def _version_sort_key(name: str) -> tuple[int, ...]:
    """Turn a ``cmdline-tools`` directory name (e.g. ``"12.0"``) into a comparable tuple.

    Plain string sorting orders ``"9.0"`` above ``"12.0"`` (lexicographic
    comparison of the leading digit), silently picking an older
    ``cmdline-tools`` version over a newer one -- version-aware
    numeric comparison avoids that.
    """
    parts = re.findall(r"\d+", name)
    return tuple(int(p) for p in parts) if parts else (0,)


@dataclass(frozen=True)
class AndroidSdkPaths:
    """Resolved paths to an Android SDK installation and its tools.

    Attributes:
        sdk_root: The SDK installation root.
        adb: Path to the ``adb`` executable.
        emulator: Path to the ``emulator`` executable.
        sdkmanager: Path to the ``sdkmanager`` script.
        avdmanager: Path to the ``avdmanager`` script.
        avd_home: Directory AVDs are stored under (``~/.android/avd`` by default).

    """

    sdk_root: Path
    adb: Path
    emulator: Path
    sdkmanager: Path
    avdmanager: Path
    avd_home: Path


class AndroidSdkLocator:
    """Finds an Android SDK installation and its command-line tools.

    :meth:`locate` resolves everything at once and raises on the first
    missing piece. Each step is also exposed as its own public method
    (:meth:`find_sdk_root`, :meth:`find_adb`, :meth:`find_emulator`,
    :meth:`find_sdkmanager`, :meth:`find_avdmanager`) so a caller that
    needs to report *which specific* component is missing --
    :class:`~ugaf.emulator.dependencies.EnvironmentChecker` -- can probe
    each independently instead of only getting the first failure.
    """

    def locate(self, sdk_root_override: str | Path | None = None) -> AndroidSdkPaths:
        """Resolve the Android SDK root and every tool path it provides.

        Args:
            sdk_root_override: An explicit SDK root, taking precedence
                over environment variables and default locations.

        Returns:
            The resolved :class:`AndroidSdkPaths`.

        Raises:
            SdkNotFoundError: If no SDK root can be determined, or a
                required tool is missing from an otherwise-found SDK.

        """
        sdk_root = self.find_sdk_root(sdk_root_override)
        return AndroidSdkPaths(
            sdk_root=sdk_root,
            adb=self.find_adb(sdk_root),
            emulator=self.find_emulator(sdk_root),
            sdkmanager=self.find_sdkmanager(sdk_root),
            avdmanager=self.find_avdmanager(sdk_root),
            avd_home=self._find_avd_home(),
        )

    def find_sdk_root(self, override: str | Path | None = None) -> Path:
        """Resolve the SDK root from an override, env vars, or default install locations."""
        candidates: list[Path] = []
        if override is not None:
            candidates.append(Path(override))
        for var in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
            value = os.environ.get(var)
            if value:
                candidates.append(Path(value))
        candidates.extend(self._default_sdk_locations())

        for candidate in candidates:
            if candidate.is_dir() and (candidate / "platform-tools").is_dir():
                return candidate

        raise SdkNotFoundError(
            "Could not locate an Android SDK installation. Set the ANDROID_HOME "
            "environment variable to your SDK root, or pass sdk_root_override "
            "explicitly. Checked: " + ", ".join(str(c) for c in candidates)
        )

    def find_adb(self, sdk_root: Path) -> Path:
        """Resolve ``adb`` from *sdk_root*'s ``platform-tools/``, falling back to ``PATH``.

        Raises:
            SdkNotFoundError: If ``adb`` is found neither under
                *sdk_root* nor on ``PATH``.

        """
        platform_tools = sdk_root / "platform-tools" / _exe("adb")
        adb = platform_tools if platform_tools.is_file() else self._find_on_path("adb")
        if adb is None:
            raise SdkNotFoundError(
                f"adb not found under {sdk_root / 'platform-tools'} or on PATH. "
                "Install the 'Android SDK Platform-Tools' package via Android "
                "Studio's SDK Manager, or `sdkmanager platform-tools`."
            )
        return adb

    def find_emulator(self, sdk_root: Path) -> Path:
        """Resolve the ``emulator`` executable from *sdk_root*.

        Raises:
            SdkNotFoundError: If the ``emulator`` package is not installed.

        """
        emulator = sdk_root / "emulator" / _exe("emulator")
        if not emulator.is_file():
            raise SdkNotFoundError(
                f"emulator executable not found at {emulator}. Install the "
                "'Android Emulator' package via Android Studio's SDK Manager, "
                "or `sdkmanager emulator`."
            )
        return emulator

    def find_sdkmanager(self, sdk_root: Path) -> Path:
        """Resolve ``sdkmanager`` from *sdk_root*'s ``cmdline-tools/``.

        Raises:
            SdkNotFoundError: If no ``cmdline-tools`` package is installed.

        """
        return self._find_cmdline_tool(sdk_root, "sdkmanager")

    def find_avdmanager(self, sdk_root: Path) -> Path:
        """Resolve ``avdmanager`` from *sdk_root*'s ``cmdline-tools/``.

        Raises:
            SdkNotFoundError: If no ``cmdline-tools`` package is installed.

        """
        return self._find_cmdline_tool(sdk_root, "avdmanager")

    def _default_sdk_locations(self) -> list[Path]:
        """Well-known per-OS default SDK install locations (Android Studio's defaults)."""
        home = Path.home()
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA")
            locations = [Path(local_app_data) / "Android" / "Sdk"] if local_app_data else []
            locations.append(home / "AppData" / "Local" / "Android" / "Sdk")
            return locations
        if sys.platform == "darwin":
            return [home / "Library" / "Android" / "sdk"]
        return [home / "Android" / "Sdk"]

    def _find_cmdline_tool(self, sdk_root: Path, tool_name: str) -> Path:
        """Locate a command-line-tools script, preferring the ``latest`` symlink/directory.

        Falls back to the highest-versioned directory under
        ``cmdline-tools/`` when ``latest`` is absent, and to a legacy
        ``tools/bin`` layout as a last resort (pre-cmdline-tools SDKs).
        """
        cmdline_tools = sdk_root / "cmdline-tools"
        search_dirs: list[Path] = []
        if (cmdline_tools / "latest").is_dir():
            search_dirs.append(cmdline_tools / "latest")
        if cmdline_tools.is_dir():
            versioned = sorted(
                (d for d in cmdline_tools.iterdir() if d.is_dir() and d.name != "latest"),
                key=lambda d: _version_sort_key(d.name),
                reverse=True,
            )
            search_dirs.extend(versioned)
        search_dirs.append(sdk_root / "tools")

        for directory in search_dirs:
            for filename in _bat_or_exe(tool_name):
                candidate = directory / "bin" / filename
                if candidate.is_file():
                    return candidate

        raise SdkNotFoundError(
            f"{tool_name} not found under {cmdline_tools} (checked {len(search_dirs)} "
            "location(s)). Install the 'Android SDK Command-line Tools' package via "
            "Android Studio's SDK Manager (Settings > Languages & Frameworks > "
            "Android SDK > SDK Tools)."
        )

    def _find_avd_home(self) -> Path:
        """Resolve the AVD storage directory (``ANDROID_AVD_HOME`` or ``~/.android/avd``)."""
        avd_home = os.environ.get("ANDROID_AVD_HOME")
        if avd_home:
            return Path(avd_home)
        android_sdk_home = os.environ.get("ANDROID_SDK_HOME")
        base = Path(android_sdk_home) if android_sdk_home else Path.home()
        return base / ".android" / "avd"

    @staticmethod
    def _find_on_path(executable: str) -> Path | None:
        """Fall back to ``PATH`` lookup when a tool isn't under the resolved SDK root."""
        found = shutil.which(_exe(executable))
        return Path(found) if found else None
