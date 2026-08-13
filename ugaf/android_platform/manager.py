"""``AndroidPlatformManager``: the single Android-domain facade over SDK tooling.

Wraps :class:`~ugaf.emulator.manager.EmulatorManager` (AVD/emulator
lifecycle), :class:`~ugaf.emulator.dependencies.EnvironmentChecker` (SDK
validation), and :class:`~ugaf.device.manager.DeviceManager` (physical +
virtual device discovery) behind Android-domain method names — "Virtual
Device", "Physical Device", "Platform Health" — rather than SDK-tool
names. Owns the emulator-side lifecycle transitions (``VALIDATING`` ->
``STARTING`` -> ... -> ``STOPPING``/``STOPPED``) on the same
:class:`~ugaf.device.lifecycle.DeviceLifecycle` instance the webapp's
device-connect pipeline uses, so there is still only one authoritative
state per device -- see ADR-021.
"""

from __future__ import annotations

from dataclasses import dataclass

from ugaf.device.lifecycle import DeviceLifecycle, DeviceState
from ugaf.device.manager import DeviceManager
from ugaf.emulator.dependencies import DependencyReport, EnvironmentChecker
from ugaf.emulator.exceptions import EmulatorManagerError
from ugaf.emulator.hardware import HardwareInfo
from ugaf.emulator.manager import EmulatorManager
from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle
from ugaf.platform.device import DeviceInfo, DeviceStatus

__all__ = [
    "AndroidPlatformManager",
    "PlatformHealth",
]


@dataclass(frozen=True)
class PlatformHealth:
    """A consolidated Android Platform health summary (the "Environment Doctor").

    Attributes:
        dependencies: Every SDK-tool dependency check (see
            :class:`~ugaf.emulator.dependencies.DependencyReport`).
        hardware: Host CPU/RAM/virtualization-acceleration capability.
        physical_device_count: Number of currently-attached physical
            phones (ADB-reachable, not an emulator serial).
        virtual_device_count: Number of currently-running emulator
            instances (ADB-reachable, emulator serial).
        overall_healthy: Whether every *blocking* dependency is present.
            Matches :attr:`DependencyReport.ready` -- Hypervisor and
            cmdline-tools-layout issues are surfaced but never block.

    """

    dependencies: DependencyReport
    hardware: HardwareInfo
    physical_device_count: int
    virtual_device_count: int
    overall_healthy: bool


class AndroidPlatformManager:
    """The one component that understands Android SDK tooling.

    Usage::

        platform = AndroidPlatformManager(emulator_manager, device_manager, lifecycle)
        health = platform.platform_health()
        avd = platform.create_virtual_device("ROG A15", "Asus", "rog_phone_9", "gaming")
        handle = platform.start_virtual_device(avd.name)
        platform.stop_virtual_device(avd.name)

    """

    def __init__(
        self,
        emulator_manager: EmulatorManager,
        device_manager: DeviceManager,
        lifecycle: DeviceLifecycle,
        environment_checker: EnvironmentChecker | None = None,
    ) -> None:
        """Wrap already-constructed managers rather than building its own.

        Args:
            emulator_manager: The AVD/emulator-process backend.
            device_manager: The shared physical+virtual device
                discovery source -- never a second, independent one.
            lifecycle: The shared :class:`DeviceLifecycle` instance
                (the same one the webapp's connect pipeline uses), so
                emulator-side transitions and device-connect
                transitions never fork into two sources of truth for
                the same device.
            environment_checker: Optional pre-built checker (mainly
                for tests); defaults to a real one.

        """
        self._emulator_manager = emulator_manager
        self._device_manager = device_manager
        self._lifecycle = lifecycle
        self._environment_checker = environment_checker or EnvironmentChecker()

    # ------------------------------------------------------------------
    # SDK validation / Environment Doctor
    # ------------------------------------------------------------------

    def environment_report(self) -> DependencyReport:
        """Return the full per-component SDK validation report."""
        return self._environment_checker.check(self._emulator_manager.sdk_paths.sdk_root)

    def platform_health(self) -> PlatformHealth:
        """Return the consolidated Android Platform health summary."""
        dependencies = self.environment_report()
        hardware = self._emulator_manager.detect_hardware()
        physical = self.list_physical_devices()
        virtual = self.list_running_virtual_devices()
        return PlatformHealth(
            dependencies=dependencies,
            hardware=hardware,
            physical_device_count=len(physical),
            virtual_device_count=len(virtual),
            overall_healthy=dependencies.ready,
        )

    # ------------------------------------------------------------------
    # Virtual Devices (AVDs)
    # ------------------------------------------------------------------

    def list_virtual_devices(self) -> list[AvdInfo]:
        """Return every known Virtual Device, including invalid/broken ones."""
        return self._emulator_manager.list()

    def create_virtual_device(
        self,
        name: str,
        manufacturer: str,
        device_name: str,
        performance_profile: str = "mid_range",
    ) -> AvdInfo:
        """Create a new Virtual Device (name sanitization handled by ``EmulatorManager``)."""
        return self._emulator_manager.create(name, manufacturer, device_name, performance_profile)

    def delete_virtual_device(self, name: str) -> None:
        """Stop (if running) and permanently delete a Virtual Device."""
        self._emulator_manager.delete(name)
        self._lifecycle.forget(name)

    def rename_virtual_device(self, name: str, new_name: str) -> None:
        """Rename a Virtual Device."""
        self._emulator_manager.rename(name, new_name)

    def start_virtual_device(self, name: str) -> EmulatorInstanceHandle:
        """Validate prerequisites, then launch a Virtual Device as a running emulator.

        Implements the "Create -> Validate -> Boot" prefix of the
        documented Emulator Lifecycle: dependencies and the AVD's
        required system image are checked *before* the emulator
        process is ever launched, so a doomed launch fails fast with a
        specific reason instead of an opaque timeout later.

        The remainder of the lifecycle (``WAITING_FOR_ADB`` ->
        ``BOOTING`` -> ``INITIALIZING`` -> ``CAPTURING_TEST_FRAME`` ->
        ``READY``) is owned by the webapp's device-connect pipeline
        once the emulator's ADB serial is known -- this method's
        ``name``-keyed lifecycle entry is deliberately forgotten once
        the process is launched, since ``adb_serial`` becomes the
        canonical key for the same physical device from that point on.

        Raises:
            EmulatorManagerError: If a blocking dependency is missing.

        """
        owner = "AndroidPlatformManager.start_virtual_device"
        self._lifecycle.transition(
            name, DeviceState.VALIDATING, "checking dependencies", owner=owner
        )
        report = self.environment_report()
        if not report.ready:
            missing = report.first_missing()
            reason = f"blocking dependency missing: {missing.name if missing else 'unknown'}"
            self._lifecycle.transition(name, DeviceState.ERROR, reason, owner=owner)
            raise EmulatorManagerError(
                f"Cannot start Virtual Device {name!r}: {reason}. "
                f"{missing.detail if missing else ''}"
            )

        self._lifecycle.transition(
            name, DeviceState.STARTING, "launching emulator process", owner=owner
        )
        try:
            handle = self._emulator_manager.start(name)
        except Exception as exc:
            self._lifecycle.transition(
                name, DeviceState.ERROR, f"failed to launch: {exc}", owner=owner
            )
            raise
        # From here on, `handle.adb_serial` is the canonical lifecycle key --
        # see the docstring above.
        self._lifecycle.forget(name)
        return handle

    def stop_virtual_device(self, name: str) -> None:
        """Gracefully shut down a running Virtual Device."""
        owner = "AndroidPlatformManager.stop_virtual_device"
        self._lifecycle.transition(name, DeviceState.STOPPING, "stopping emulator", owner=owner)
        try:
            self._emulator_manager.stop(name)
        except Exception as exc:
            self._lifecycle.transition(
                name, DeviceState.ERROR, f"failed to stop: {exc}", owner=owner
            )
            raise
        self._lifecycle.transition(name, DeviceState.STOPPED, "emulator stopped", owner=owner)

    def list_running_virtual_devices(self) -> list[AvdInfo]:
        """Return only Virtual Devices with a currently-running emulator process."""
        return [avd for avd in self.list_virtual_devices() if avd.running]

    # ------------------------------------------------------------------
    # Physical devices
    # ------------------------------------------------------------------

    def list_physical_devices(self) -> list[DeviceInfo]:
        """Return every ADB-reachable device that is not an emulator serial.

        Emulator ADB serials always look like ``emulator-<port>`` --
        anything else reported by :class:`~ugaf.device.manager.DeviceManager`
        (USB or ADB-over-Wi-Fi) is a physical phone.
        """
        return [d for d in self._device_manager.discover() if not d.id.startswith("emulator-")]

    def list_connected_devices(self) -> list[DeviceInfo]:
        """Return every currently-online device (physical or virtual), from one source."""
        return [d for d in self._device_manager.discover() if d.status is DeviceStatus.ONLINE]
