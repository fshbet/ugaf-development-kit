"""Root-cause boot diagnostics for the Android emulator boot sequence.

Before this module, a boot that never completed was reported as a bare
"did not finish booting within the configured timeout" — accurate, but
useless for knowing *why*: an instantly-crashed emulator process, ADB
never seeing the device, ``sys.boot_completed`` genuinely stuck, or the
launcher simply taking a moment longer than the boot properties suggest
all looked identical. :class:`BootMonitor` polls every real signal
independently and reports exactly which one never arrived (ADR-023).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

from ugaf.core.logger import Logger, get_logger
from ugaf.device.manager import DeviceManager
from ugaf.emulator.manager import EmulatorManager
from ugaf.platform.device import DeviceStatus

__all__ = [
    "BootDiagnostics",
    "BootMonitor",
]

_POLL_INTERVAL_SECONDS = 2.0

_STAGE_RECOMMENDATIONS = {
    "emulator_process": (
        "The emulator process exited before booting. Open the emulator log to see "
        "why it crashed, then retry boot."
    ),
    "adb_visibility": (
        "ADB never reported this device as online. Try restarting the ADB server, "
        "or check the emulator window for a stuck boot/crash dialog."
    ),
    "boot_completed": (
        "Android boot exceeded the configured timeout. Open the emulator log, retry "
        "boot, or reset the Virtual Device if this repeats."
    ),
    "bootanim": (
        "The boot animation never finished. The emulator may be under-resourced for "
        "its performance profile -- consider a lighter profile."
    ),
    "launcher": (
        "The system booted but the launcher never appeared in the foreground. Check "
        "for a crashed launcher or a stuck first-run dialog."
    ),
}


@dataclass(frozen=True)
class BootDiagnostics:
    """A snapshot of every real boot signal collected during one boot-wait attempt.

    Attributes:
        emulator_process_running: Whether the ``emulator``/``qemu``
            process is still alive.
        adb_visible: Whether ADB currently lists this serial at all.
        adb_status: The raw ADB status (``"online"``/``"offline"``/
            ``"unauthorized"``), when visible.
        boot_completed: ``getprop sys.boot_completed == "1"``.
        dev_bootcomplete: ``getprop dev.bootcomplete == "1"`` -- a
            second, independently-set property checked in addition to
            ``sys.boot_completed`` since either can lag the other
            slightly on some system images.
        bootanim_stopped: ``getprop init.svc.bootanim == "stopped"``,
            or ``None`` if not yet checked (a boot-completed prop being
            false makes this check moot).
        foreground_package: The foreground activity's package, once
            ``dumpsys window`` reports one — evidence the launcher (or
            any app) is actually visible, not just that boot properties
            flipped.
        elapsed_seconds: Time since :meth:`BootMonitor.wait_for_boot`
            was called.
        failed_stage: ``None`` if every signal succeeded (fully
            booted); otherwise the first stage, in check order, that
            did not — one of ``"emulator_process"``, ``"adb_visibility"``,
            ``"boot_completed"``, ``"bootanim"``, ``"launcher"``.

    """

    emulator_process_running: bool
    adb_visible: bool
    adb_status: str | None
    boot_completed: bool
    dev_bootcomplete: bool
    bootanim_stopped: bool | None
    foreground_package: str | None
    elapsed_seconds: float
    failed_stage: str | None

    @property
    def recommended_action(self) -> str | None:
        """A human-readable next step for :attr:`failed_stage`, or ``None`` if booted."""
        if self.failed_stage is None:
            return None
        return _STAGE_RECOMMENDATIONS.get(self.failed_stage, "Retry boot.")


class BootMonitor:
    """Polls every real Android boot signal, identifying exactly which stage is stuck.

    Usage::

        monitor = BootMonitor()
        diagnostics = monitor.wait_for_boot(
            device_manager, emulator_manager, "MyAvd", "emulator-5554", timeout=180
        )
        if diagnostics.failed_stage is not None:
            print(diagnostics.recommended_action)

    """

    def __init__(
        self, logger: Logger | None = None, poll_interval: float = _POLL_INTERVAL_SECONDS
    ) -> None:
        """Initialize the monitor with an optional logger/poll-interval override."""
        self._logger = logger or get_logger()
        self._poll_interval = poll_interval

    def wait_for_boot(
        self,
        device_manager: DeviceManager,
        emulator_manager: EmulatorManager,
        avd_name: str,
        adb_serial: str,
        timeout: float,
    ) -> BootDiagnostics:
        """Poll every boot signal until fully booted, the timeout elapses, or the process dies.

        Args:
            device_manager: Source of live ADB device status.
            emulator_manager: Source of emulator-process liveness
                (``is_running``).
            avd_name: The AVD to poll process liveness for.
            adb_serial: The ADB serial to poll device/boot status for.
            timeout: Maximum seconds to wait.

        Returns:
            The final :class:`BootDiagnostics` snapshot — fully booted
            (``failed_stage is None``) or whichever stage never
            completed.

        """
        start = time.monotonic()
        deadline = start + timeout
        diagnostics = self._probe(device_manager, emulator_manager, avd_name, adb_serial, start)
        while diagnostics.failed_stage is not None and time.monotonic() < deadline:
            # A crashed process will never progress further -- no point
            # burning the rest of the timeout polling a dead emulator.
            if not diagnostics.emulator_process_running:
                break
            time.sleep(self._poll_interval)
            diagnostics = self._probe(device_manager, emulator_manager, avd_name, adb_serial, start)

        if diagnostics.failed_stage is not None:
            self._logger.warning(
                "boot_monitor.boot_incomplete",
                avd=avd_name,
                device=adb_serial,
                failed_stage=diagnostics.failed_stage,
                elapsed_seconds=diagnostics.elapsed_seconds,
            )
        else:
            self._logger.info(
                "boot_monitor.boot_complete",
                avd=avd_name,
                device=adb_serial,
                elapsed_seconds=diagnostics.elapsed_seconds,
            )
        return diagnostics

    def _probe(
        self,
        device_manager: DeviceManager,
        emulator_manager: EmulatorManager,
        avd_name: str,
        adb_serial: str,
        start_time: float,
    ) -> BootDiagnostics:
        """Check every signal once, stopping at the first one that fails."""
        elapsed = time.monotonic() - start_time

        if not emulator_manager.is_running(avd_name):
            return BootDiagnostics(
                emulator_process_running=False,
                adb_visible=False,
                adb_status=None,
                boot_completed=False,
                dev_bootcomplete=False,
                bootanim_stopped=None,
                foreground_package=None,
                elapsed_seconds=elapsed,
                failed_stage="emulator_process",
            )

        device = next((d for d in device_manager.discover() if d.id == adb_serial), None)
        if device is None or device.status is not DeviceStatus.ONLINE:
            return BootDiagnostics(
                emulator_process_running=True,
                adb_visible=device is not None,
                adb_status=device.status.value if device else None,
                boot_completed=False,
                dev_bootcomplete=False,
                bootanim_stopped=None,
                foreground_package=None,
                elapsed_seconds=elapsed,
                failed_stage="adb_visibility",
            )

        boot_completed = self._prop_is_one(device_manager, adb_serial, "sys.boot_completed")
        dev_bootcomplete = self._prop_is_one(device_manager, adb_serial, "dev.bootcomplete")
        if not (boot_completed and dev_bootcomplete):
            return BootDiagnostics(
                emulator_process_running=True,
                adb_visible=True,
                adb_status="online",
                boot_completed=boot_completed,
                dev_bootcomplete=dev_bootcomplete,
                bootanim_stopped=None,
                foreground_package=None,
                elapsed_seconds=elapsed,
                failed_stage="boot_completed",
            )

        bootanim_stopped = self._bootanim_stopped(device_manager, adb_serial)
        if not bootanim_stopped:
            return BootDiagnostics(
                emulator_process_running=True,
                adb_visible=True,
                adb_status="online",
                boot_completed=True,
                dev_bootcomplete=True,
                bootanim_stopped=False,
                foreground_package=None,
                elapsed_seconds=elapsed,
                failed_stage="bootanim",
            )

        foreground_package = self._foreground_package(device_manager, adb_serial)
        if not foreground_package:
            return BootDiagnostics(
                emulator_process_running=True,
                adb_visible=True,
                adb_status="online",
                boot_completed=True,
                dev_bootcomplete=True,
                bootanim_stopped=True,
                foreground_package=None,
                elapsed_seconds=elapsed,
                failed_stage="launcher",
            )

        return BootDiagnostics(
            emulator_process_running=True,
            adb_visible=True,
            adb_status="online",
            boot_completed=True,
            dev_bootcomplete=True,
            bootanim_stopped=True,
            foreground_package=foreground_package,
            elapsed_seconds=elapsed,
            failed_stage=None,
        )

    @staticmethod
    def _prop_is_one(device_manager: DeviceManager, adb_serial: str, prop: str) -> bool:
        try:
            value = device_manager.shell_sync(adb_serial, "getprop", prop)
        except Exception:  # noqa: BLE001 - a transient shell failure just means "not yet"
            return False
        return value.strip() == "1"

    @staticmethod
    def _bootanim_stopped(device_manager: DeviceManager, adb_serial: str) -> bool:
        try:
            value = device_manager.shell_sync(adb_serial, "getprop", "init.svc.bootanim")
        except Exception:  # noqa: BLE001 - treated as "still running" until proven otherwise
            return False
        return value.strip() == "stopped"

    @staticmethod
    def _foreground_package(device_manager: DeviceManager, adb_serial: str) -> str | None:
        try:
            focus = device_manager.shell_sync(
                adb_serial, "dumpsys", "window", "|", "grep", "mCurrentFocus"
            )
        except Exception:  # noqa: BLE001 - best-effort; absence just means "not confirmed yet"
            return None
        match = re.search(r"(\S+)/\S+\}", focus)
        return match.group(1) if match else None
