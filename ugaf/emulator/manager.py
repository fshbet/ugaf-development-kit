"""Emulator Manager: the clean, provider-agnostic Android emulator SDK API.

The single entry point the webapp (and any future caller) uses for
everything emulator-related — never talks to ``avdmanager``/``emulator``/
``sdkmanager`` directly, exactly mirroring how
:class:`~ugaf.apps.manager.ApplicationManager` is the only thing that
knows how to launch an Android app. All device/performance data comes
from :class:`~ugaf.emulator.profiles.DeviceProfileManager` /
:class:`~ugaf.emulator.performance.PerformanceProfileManager`; the
actual emulator backend is whichever :class:`~ugaf.emulator.provider.EmulatorProvider`
is registered under ``provider_name`` (``"android_studio"`` today).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from ugaf.core.logger import Logger, get_logger
from ugaf.emulator.android_versions import AndroidVersionManager
from ugaf.emulator.dependencies import DependencyReport, EnvironmentChecker
from ugaf.emulator.hardware import HardwareDetector, HardwareInfo
from ugaf.emulator.naming import sanitize_avd_name
from ugaf.emulator.performance import PerformanceProfileManager
from ugaf.emulator.profiles import DeviceProfileManager
from ugaf.emulator.provider import emulator_registry
from ugaf.emulator.sdk_locator import AndroidSdkLocator, AndroidSdkPaths
from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle, PerformanceProfile, SystemImageInfo

__all__ = [
    "EmulatorManager",
]

_DEFAULT_SETTINGS_PATH = Path("config/emulator_settings.yaml")


def _load_settings(path: Path) -> dict[str, Any]:
    """Load ``config/emulator_settings.yaml``'s ``emulator:`` section, if present."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    settings = data.get("emulator")
    return dict(settings) if settings else {}


class EmulatorManager:
    """Facade over device profiles, performance profiles, and an emulator provider.

    Usage::

        manager = EmulatorManager()
        profile = manager.device_profiles.get("Samsung", "galaxy_s25_ultra")
        avd = manager.create("GalaxyS25Ultra_01", "Samsung", "galaxy_s25_ultra", "gaming")
        handle = manager.start(avd.name)
        manager.wait_until_booted(avd.name, timeout=180)
        manager.install_apk(avd.name, "app.apk")
        manager.stop(avd.name)

    """

    def __init__(
        self,
        sdk_root: str | Path | None = None,
        provider_name: str | None = None,
        settings_path: Path | str | None = None,
        device_profiles: DeviceProfileManager | None = None,
        performance_profiles: PerformanceProfileManager | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Locate the SDK, load profiles, and construct the configured provider.

        Args:
            sdk_root: Explicit Android SDK root. When ``None``, resolved
                from ``config/emulator_settings.yaml``'s ``sdk_root``,
                then environment variables/default install locations
                (see :class:`~ugaf.emulator.sdk_locator.AndroidSdkLocator`).
            provider_name: Which registered :class:`~ugaf.emulator.provider.EmulatorProvider`
                to use. Defaults to ``config/emulator_settings.yaml``'s
                ``default_provider`` (``"android_studio"`` out of the box).
            settings_path: Path to ``emulator_settings.yaml`` (defaults
                to ``config/emulator_settings.yaml``).
            device_profiles: Optional pre-built profile manager (mainly for tests).
            performance_profiles: Optional pre-built profile manager (mainly for tests).
            logger: Optional logger.

        Raises:
            SdkNotFoundError: If no Android SDK installation can be located.

        """
        self._logger = logger or get_logger()
        settings = _load_settings(
            Path(settings_path) if settings_path is not None else _DEFAULT_SETTINGS_PATH
        )

        resolved_sdk_root = sdk_root if sdk_root is not None else settings.get("sdk_root")
        self._sdk_paths = AndroidSdkLocator().locate(resolved_sdk_root)

        self.device_profiles = device_profiles or DeviceProfileManager()
        self.performance_profiles = performance_profiles or PerformanceProfileManager()
        self.hardware = HardwareDetector(logger=self._logger)
        self._android_versions = AndroidVersionManager(self._sdk_paths, logger=self._logger)

        resolved_provider = provider_name or settings.get("default_provider", "android_studio")
        first_console_port = int(settings.get("first_console_port", 5554))
        self._boot_timeout = float(settings.get("boot_timeout_seconds", 180.0))
        self._provider = emulator_registry.create(
            resolved_provider,
            self._sdk_paths,
            self._android_versions,
            logger=self._logger,
            first_console_port=first_console_port,
            disable_vulkan=bool(settings.get("disable_vulkan", True)),
        )

        self._logger.info(
            "emulator_manager.initialized",
            sdk_root=str(self._sdk_paths.sdk_root),
            provider=resolved_provider,
        )

    @property
    def sdk_paths(self) -> AndroidSdkPaths:
        """Return the resolved Android SDK tool paths."""
        return self._sdk_paths

    @property
    def boot_timeout(self) -> float:
        """Return the configured boot timeout in seconds (``emulator_settings.yaml``)."""
        return self._boot_timeout

    # ------------------------------------------------------------------
    # Dependency / environment checking (ATDD acceptance criteria)
    # ------------------------------------------------------------------

    def check_dependencies(self) -> DependencyReport:
        """Probe every Emulator Manager dependency (Android Studio/SDK/tools) independently.

        Since this method only runs after ``__init__`` already resolved
        ``self._sdk_paths`` successfully, every blocking component is
        necessarily present -- this is mainly useful for confirming
        Android Studio's status without a second SDK-root resolution.
        Callers that need a full report *before* knowing whether
        :class:`EmulatorManager` can even be constructed (e.g. the
        webapp, when the SDK might be entirely missing) should use
        :class:`~ugaf.emulator.dependencies.EnvironmentChecker` directly
        instead of going through this class.
        """
        return EnvironmentChecker().check(self._sdk_paths.sdk_root)

    def check_system_image(self, manufacturer: str, device_name: str) -> bool:
        """Return whether the system image a device profile needs is already installed.

        Does not install anything -- :meth:`create` already does that
        automatically. This is for surfacing the "Required system image
        installed" acceptance-checklist item to a user *before* they
        click Create, so they know a first-time create for that
        device/version pair will need to download something.
        """
        profile = self.device_profiles.get(manufacturer, device_name)
        tag = "google_apis_playstore" if profile.play_store else "google_apis"
        return self._android_versions.is_installed(profile.api_level, tag, profile.abi)

    # ------------------------------------------------------------------
    # Hardware / performance recommendation
    # ------------------------------------------------------------------

    def detect_hardware(self) -> HardwareInfo:
        """Detect current host CPU/RAM/virtualization-acceleration capability."""
        return self.hardware.detect(self._sdk_paths.emulator)

    def recommend_performance_profile(self) -> PerformanceProfile:
        """Return the performance preset recommended for this host's detected hardware."""
        info = self.detect_hardware()
        name = self.hardware.recommend_performance_profile(info)
        return self.performance_profiles.get(name)

    # ------------------------------------------------------------------
    # Android versions
    # ------------------------------------------------------------------

    def list_android_versions(self) -> list[SystemImageInfo]:
        """Return every Android system image, installed or installable."""
        return self._android_versions.list_available()

    def list_installed_android_versions(self) -> list[SystemImageInfo]:
        """Return only the Android system images already installed locally."""
        return self._android_versions.list_installed()

    # ------------------------------------------------------------------
    # Device / performance profile lookup
    # ------------------------------------------------------------------

    def list_manufacturers(self) -> list[str]:
        """Return every supported device manufacturer."""
        return self.device_profiles.manufacturers()

    def list_devices(self, manufacturer: str) -> list[Any]:
        """Return every device profile for *manufacturer*."""
        return self.device_profiles.devices(manufacturer)

    def list_performance_profiles(self) -> list[str]:
        """Return every performance preset name."""
        return self.performance_profiles.names()

    # ------------------------------------------------------------------
    # AVD lifecycle -- the SDK API from the sprint directive
    # ------------------------------------------------------------------

    def list(self) -> list[AvdInfo]:
        """Return every known AVD, including invalid/broken ones."""
        return self._provider.list()

    def create(
        self,
        name: str,
        manufacturer: str,
        device_name: str,
        performance_profile_name: str = "mid_range",
        force: bool = False,
    ) -> AvdInfo:
        """Create a new AVD from a manufacturer/device profile and a performance preset.

        *name* is automatically sanitized into a valid ``avdmanager``
        identifier (e.g. ``"ROG A15"`` -> ``"ROG_A15"``) -- the user
        should never need to know or work around ``avdmanager``'s naming
        rules themselves. When sanitization changed the name, the
        original is preserved on the returned :class:`AvdInfo`'s
        ``display_name`` so the UI can still show what the user typed.
        """
        sanitized_name = sanitize_avd_name(name)
        device_profile = self.device_profiles.get(manufacturer, device_name)
        performance_profile = self.performance_profiles.get(performance_profile_name)
        avd = self._provider.create(
            sanitized_name, device_profile, performance_profile, force=force
        )
        if sanitized_name != name:
            self._logger.info(
                "emulator_manager.avd_name_sanitized", requested=name, sanitized=sanitized_name
            )
            avd = replace(avd, display_name=name)
        return avd

    def delete(self, name: str) -> None:
        """Stop (if running) and permanently delete an AVD."""
        self._provider.delete(name)

    def rename(self, name: str, new_name: str) -> None:
        """Rename an AVD."""
        self._provider.rename(name, new_name)

    def clone(self, source: str, target: str) -> AvdInfo:
        """Duplicate an AVD under a new name."""
        return self._provider.clone(source, target)

    def update_hardware(self, name: str, performance_profile_name: str) -> None:
        """Apply a different performance preset to an existing AVD."""
        performance_profile = self.performance_profiles.get(performance_profile_name)
        self._provider.update_hardware(name, performance_profile)

    def start(self, name: str) -> EmulatorInstanceHandle:
        """Launch an AVD as a new emulator instance."""
        return self._provider.start(name)

    def stop(self, name: str) -> None:
        """Gracefully shut down a running AVD."""
        self._provider.stop(name)

    def is_running(self, name: str) -> bool:
        """Return whether an AVD currently has a running emulator process."""
        return self._provider.is_running(name)

    def detect_crash(self, name: str) -> bool:
        """Return whether a launched AVD has crashed unexpectedly."""
        return self._provider.detect_crash(name)

    def wait_until_booted(self, name: str, timeout: float | None = None) -> bool:
        """Block until a running AVD finishes booting, or the configured timeout elapses."""
        return self._provider.wait_until_booted(
            name, timeout if timeout is not None else self._boot_timeout
        )

    def install_apk(self, name: str, apk_path: Path | str) -> None:
        """Install an APK onto a running AVD."""
        self._provider.install_apk(name, apk_path)

    def push(self, name: str, source: Path | str, destination: str) -> None:
        """Push a file to a running AVD."""
        self._provider.push(name, source, destination)

    def pull(self, name: str, source: str, destination: Path | str) -> None:
        """Pull a file from a running AVD."""
        self._provider.pull(name, source, destination)
