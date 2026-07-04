"""Android Version Manager: detects installed system images and downloads missing ones.

Wraps ``sdkmanager`` — never trusts a static list of "supported Android
versions" for what's actually installed, since that can only be known
by asking the SDK itself. ``config/android_versions.yaml`` supplies
only the API-level-to-marketing-name mapping (reference data, not a
device/emulator list) used to make output human-readable.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

from ugaf.core.logger import Logger, get_logger
from ugaf.emulator.exceptions import EmulatorCommandError, SystemImageNotAvailableError
from ugaf.emulator.sdk_locator import AndroidSdkPaths
from ugaf.emulator.types import SystemImageInfo

__all__ = [
    "AndroidVersionManager",
]

_SYSTEM_IMAGE_RE = re.compile(
    r"^system-images;android-(?P<api>\d+);(?P<tag>[\w.-]+);(?P<abi>[\w-]+)$"
)
_VERSION_NAMES_PATH = Path("config/android_versions.yaml")


class AndroidVersionManager:
    """Detects installed Android system images and installs missing ones via ``sdkmanager``."""

    def __init__(
        self,
        sdk_paths: AndroidSdkPaths,
        version_names_path: Path | str | None = None,
        logger: Logger | None = None,
        timeout: float = 60.0,
    ) -> None:
        """Bind the manager to a resolved SDK installation.

        Args:
            sdk_paths: Resolved SDK tool paths (from
                :class:`~ugaf.emulator.sdk_locator.AndroidSdkLocator`).
            version_names_path: Path to the API-level -> marketing-name
                YAML reference (defaults to ``config/android_versions.yaml``).
            logger: Optional logger.
            timeout: Timeout in seconds for ``sdkmanager`` invocations
                (downloads use a longer timeout, see :meth:`ensure_installed`).

        """
        self._sdk_paths = sdk_paths
        self._logger = logger or get_logger()
        self._timeout = timeout
        self._version_names = self._load_version_names(
            Path(version_names_path) if version_names_path is not None else _VERSION_NAMES_PATH
        )

    def version_name(self, api_level: int) -> str | None:
        """Return the marketing name for *api_level* (e.g. ``"Android 15"``), if known."""
        return self._version_names.get(api_level)

    def list_installed(self) -> list[SystemImageInfo]:
        """Return every system image currently installed."""
        return [image for image in self._list_all() if image.installed]

    def list_available(self) -> list[SystemImageInfo]:
        """Return every system image installed or installable (the full catalog)."""
        return self._list_all()

    def is_installed(self, api_level: int, tag: str, abi: str) -> bool:
        """Return whether the given system image is currently installed."""
        package_path = self._package_path(api_level, tag, abi)
        return any(
            image.package_path == package_path and image.installed for image in self._list_all()
        )

    def ensure_installed(
        self, api_level: int, tag: str = "google_apis_playstore", abi: str = "x86_64"
    ) -> SystemImageInfo:
        """Install the given system image via ``sdkmanager`` if not already present.

        Args:
            api_level: Numeric Android API level.
            tag: System image flavor (``"google_apis_playstore"``,
                ``"google_apis"``, ``"default"``).
            abi: System image ABI (e.g. ``"x86_64"``, ``"arm64-v8a"``).

        Returns:
            The now-installed :class:`~ugaf.emulator.types.SystemImageInfo`.

        Raises:
            SystemImageNotAvailableError: If *sdkmanager* has no such
                package in its catalog (nothing to download).
            EmulatorCommandError: If the download/install itself fails.

        """
        package_path = self._package_path(api_level, tag, abi)
        catalog = {image.package_path: image for image in self._list_all()}

        existing = catalog.get(package_path)
        if existing is not None and existing.installed:
            return existing
        if existing is None:
            raise SystemImageNotAvailableError(
                f"{package_path!r} is not in the sdkmanager catalog for this SDK "
                "(check the API level/tag/ABI combination)"
            )

        self._logger.info("android_version_manager.installing", package=package_path)
        try:
            subprocess.run(
                [str(self._sdk_paths.sdkmanager), "--install", package_path],
                input="y\n" * 20,
                capture_output=True,
                text=True,
                timeout=600.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EmulatorCommandError(
                f"sdkmanager --install {package_path} failed: {exc}"
            ) from exc

        refreshed = {image.package_path: image for image in self._list_all()}
        installed = refreshed.get(package_path)
        if installed is None or not installed.installed:
            raise EmulatorCommandError(
                f"sdkmanager reported success but {package_path!r} is still not installed"
            )
        self._logger.info("android_version_manager.installed", package=package_path)
        return installed

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _package_path(self, api_level: int, tag: str, abi: str) -> str:
        return f"system-images;android-{api_level};{tag};{abi}"

    def _list_all(self) -> list[SystemImageInfo]:
        """Run ``sdkmanager --list`` and parse every system-image line."""
        try:
            result = subprocess.run(
                [str(self._sdk_paths.sdkmanager), "--list"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise EmulatorCommandError(f"sdkmanager --list failed: {exc}") from exc

        return self._parse_list_output(result.stdout)

    def _parse_list_output(self, output: str) -> list[SystemImageInfo]:
        """Parse the ``Installed``/``Available Packages`` sections of ``sdkmanager --list`` output.

        ``sdkmanager --list`` lists the *entire* catalog under
        "Available Packages", including packages already installed
        (they appear under "Installed packages" too) -- so an
        already-installed image's ``package_path`` is seen twice, once
        with ``installed=True`` and once with ``installed=False``.
        Deduping keeps the installed record rather than whichever one
        happened to be parsed last, which previously made
        :meth:`is_installed`/:meth:`ensure_installed` see a real,
        already-installed system image as missing.
        """
        images: dict[str, SystemImageInfo] = {}
        installed = True
        for line in output.splitlines():
            lowered = line.strip().lower()
            if lowered.startswith("installed packages"):
                installed = True
                continue
            if lowered.startswith("available packages"):
                installed = False
                continue
            if "|" not in line:
                continue
            columns = [c.strip() for c in line.split("|")]
            if len(columns) < 2 or not columns[0]:
                continue
            match = _SYSTEM_IMAGE_RE.match(columns[0])
            if match is None:
                continue
            api_level = int(match.group("api"))
            package_path = columns[0]
            if installed or package_path not in images:
                images[package_path] = SystemImageInfo(
                    api_level=api_level,
                    version_name=self.version_name(api_level),
                    tag=match.group("tag"),
                    abi=match.group("abi"),
                    installed=installed,
                    package_path=package_path,
                )
        return list(images.values())

    @staticmethod
    def _load_version_names(path: Path) -> dict[int, str]:
        """Load the API-level -> marketing-name reference mapping."""
        if not path.is_file():
            return {}
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        versions = data.get("versions") or {}
        return {int(api): str(name) for api, name in versions.items()}
