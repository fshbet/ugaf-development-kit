"""Emulator provider abstraction: the seam for supporting emulator backends.

Mirrors :class:`ugaf.vision.screenshot.ScreenshotProvider` /
:class:`ugaf.platform.device.DeviceProvider` exactly: a narrow ABC plus
a name-keyed :class:`~ugaf.platform.registry.AdapterRegistry`. Today
only :class:`~ugaf.emulator.providers.android_studio.AndroidStudioProvider`
is registered (``"android_studio"``); adding a future backend (Windows
Hypervisor Emulator, Google Play Emulator, BlueStacks, LDPlayer, MuMu,
Nox, Genymotion, Waydroid) means implementing this interface and
registering it under a new name — :class:`~ugaf.emulator.manager.EmulatorManager`
and every caller stay unchanged.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ugaf.emulator.types import AvdInfo, DeviceProfile, EmulatorInstanceHandle, PerformanceProfile
from ugaf.platform.registry import AdapterRegistry

__all__ = [
    "EmulatorProvider",
    "emulator_registry",
]


class EmulatorProvider(ABC):
    """Abstract base class for Android emulator backends."""

    @abstractmethod
    def list(self) -> list[AvdInfo]:
        """Return every known virtual device, including invalid/broken ones."""

    @abstractmethod
    def create(
        self,
        name: str,
        device_profile: DeviceProfile,
        performance_profile: PerformanceProfile,
        force: bool = False,
    ) -> AvdInfo:
        """Create a new virtual device from a device + performance profile.

        Args:
            name: The new AVD's unique name.
            device_profile: Identity/hardware spec to build from.
            performance_profile: Resource limits to apply.
            force: If ``True``, overwrite an existing AVD of the same name.

        """

    @abstractmethod
    def delete(self, name: str) -> None:
        """Permanently delete a virtual device."""

    @abstractmethod
    def rename(self, name: str, new_name: str) -> None:
        """Rename a virtual device."""

    @abstractmethod
    def clone(self, source: str, target: str) -> AvdInfo:
        """Duplicate a virtual device under a new name."""

    @abstractmethod
    def update_hardware(self, name: str, performance_profile: PerformanceProfile) -> None:
        """Apply a new performance profile to an existing (stopped) virtual device."""

    @abstractmethod
    def start(self, name: str) -> EmulatorInstanceHandle:
        """Launch a virtual device, allocating a free port pair for this instance."""

    @abstractmethod
    def stop(self, name: str) -> None:
        """Gracefully shut down a running virtual device."""

    @abstractmethod
    def is_running(self, name: str) -> bool:
        """Return whether a virtual device currently has a running emulator process."""

    @abstractmethod
    def detect_crash(self, name: str) -> bool:
        """Return whether a virtual device this provider launched has crashed unexpectedly."""

    @abstractmethod
    def wait_until_booted(self, name: str, timeout: float) -> bool:
        """Block until a running virtual device finishes booting Android, or *timeout* elapses."""

    @abstractmethod
    def install_apk(self, name: str, apk_path: Path | str) -> None:
        """Install an APK onto a running virtual device."""

    @abstractmethod
    def push(self, name: str, source: Path | str, destination: str) -> None:
        """Push a file to a running virtual device."""

    @abstractmethod
    def pull(self, name: str, source: str, destination: Path | str) -> None:
        """Pull a file from a running virtual device."""


emulator_registry: AdapterRegistry[EmulatorProvider] = AdapterRegistry(
    EmulatorProvider  # type: ignore[type-abstract]
)
