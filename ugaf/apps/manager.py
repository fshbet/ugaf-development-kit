"""Application Manager: Android application lifecycle, reusable across every automation.

The Core Engine and game plugins never run raw ``adb`` (or any other
transport's) commands to install-check, launch, or stop an app —
they go through :class:`ApplicationManager`, which itself only talks
to :class:`~ugaf.device.manager.DeviceManager` (never a transport
directly), exactly mirroring how plugins never talk to ADB directly
for device enumeration. One :class:`ApplicationManager` serves every
plugin/application (Shadow Fight 3, Calculator, Chrome, ...) — nothing
here is game-specific; per-app behaviour comes entirely from the
:class:`~ugaf.apps.types.AppDefinition` passed in.
"""

from __future__ import annotations

import asyncio
import re
import time

from ugaf.apps.types import AppDefinition, LaunchResult
from ugaf.core.logger import Logger, get_logger
from ugaf.device.exceptions import DeviceManagerError
from ugaf.device.manager import DeviceManager

__all__ = [
    "ApplicationManager",
]

# Matches the focused-window line from `dumpsys window windows`, e.g.
# "mCurrentFocus=Window{... u0 com.example.app/com.example.app.MainActivity}"
_CURRENT_FOCUS_RE = re.compile(r"mCurrentFocus=.*?\s([\w.]+)/([\w.$]+)\}")
# Fallback: the resumed-activity line from `dumpsys activity activities`,
# present across a wider range of Android versions than mCurrentFocus.
_RESUMED_ACTIVITY_RE = re.compile(r"(?:mResumedActivity|topResumedActivity).*?\s([\w.]+)/([\w.$]+)")

_POLL_INTERVAL = 0.5


class ApplicationManager:
    """Detects, launches, verifies, and stops Android applications.

    Usage::

        manager = ApplicationManager(device_manager)
        app = AppDefinition.load(Path("games/shadow_fight_3/app.yaml"))
        result = await manager.launch_and_wait(device_id, app)
        if result.success:
            ...  # automation is safe to begin
        await manager.stop(device_id, app.package)  # optional

    """

    def __init__(self, device_manager: DeviceManager, logger: Logger | None = None) -> None:
        """Bind the manager to a :class:`DeviceManager` for shell execution."""
        self._device_manager = device_manager
        self._logger = logger or get_logger()

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    async def list_packages(self, device_id: str, third_party_only: bool = True) -> list[str]:
        """Return every installed package name on *device_id*.

        Args:
            device_id: The target device.
            third_party_only: If ``True`` (default), excludes
                system/pre-installed packages (``pm list packages -3``)
                — the set a user actually installed themselves.

        """
        args = ["pm", "list", "packages"]
        if third_party_only:
            args.append("-3")
        output = await self._device_manager.execute_shell(device_id, *args)
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line[len("package:") :])
        return packages

    async def is_installed(self, device_id: str, package: str) -> bool:
        """Return whether *package* is installed on *device_id*."""
        output = await self._device_manager.execute_shell(
            device_id, "pm", "list", "packages", package
        )
        target = f"package:{package}"
        return any(line.strip() == target for line in output.splitlines())

    async def get_version(self, device_id: str, package: str) -> str | None:
        """Return *package*'s ``versionName`` on *device_id*, or ``None`` if unavailable."""
        try:
            output = await self._device_manager.execute_shell(
                device_id, "dumpsys", "package", package
            )
        except DeviceManagerError:
            return None
        match = re.search(r"versionName=(\S+)", output)
        return match.group(1) if match else None

    async def foreground_package(self, device_id: str) -> str | None:
        """Return the package currently in the foreground on *device_id*, if determinable."""
        try:
            output = await self._device_manager.execute_shell(
                device_id, "dumpsys", "window", "windows"
            )
        except DeviceManagerError:
            output = ""
        match = _CURRENT_FOCUS_RE.search(output)
        if match is None:
            try:
                output = await self._device_manager.execute_shell(
                    device_id, "dumpsys", "activity", "activities"
                )
            except DeviceManagerError:
                return None
            match = _RESUMED_ACTIVITY_RE.search(output)
        return match.group(1) if match else None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def launch(self, device_id: str, app: AppDefinition) -> None:
        """Start *app* once, without waiting for it to reach the foreground.

        Prefers ``app.launch_activity`` (``am start -n pkg/activity``)
        when given; otherwise launches via the app's own launcher
        intent (``monkey -p pkg -c android.intent.category.LAUNCHER
        1``), which works for any installed app without needing to
        know its main activity.
        """
        if app.launch_activity:
            await self._device_manager.execute_shell(
                device_id, "am", "start", "-n", f"{app.package}/{app.launch_activity}"
            )
        else:
            await self._device_manager.execute_shell(
                device_id,
                "monkey",
                "-p",
                app.package,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            )

    async def wait_for_foreground(
        self, device_id: str, package: str, timeout: float, poll_interval: float = _POLL_INTERVAL
    ) -> bool:
        """Poll :meth:`foreground_package` until it matches *package*, or *timeout* elapses."""
        deadline = time.monotonic() + timeout
        while True:
            if await self.foreground_package(device_id) == package:
                return True
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(poll_interval)

    async def launch_and_wait(self, device_id: str, app: AppDefinition) -> LaunchResult:
        """Run the full startup workflow: installed -> launch -> verify foreground.

        Retries up to ``app.launch_retries`` additional times if the
        app does not reach the foreground within ``app.launch_timeout``
        seconds. Automation must never begin until this returns a
        successful :class:`LaunchResult`.
        """
        start = time.monotonic()

        if not await self.is_installed(device_id, app.package):
            return LaunchResult(
                success=False,
                package=app.package,
                foreground_package=None,
                attempts=0,
                elapsed=time.monotonic() - start,
                error=f"{app.package!r} is not installed on {device_id!r}",
            )

        last_error: str | None = None
        total_attempts = app.launch_retries + 1
        for attempt in range(1, total_attempts + 1):
            await self.launch(device_id, app)
            reached = await self.wait_for_foreground(device_id, app.package, app.launch_timeout)
            if reached:
                return LaunchResult(
                    success=True,
                    package=app.package,
                    foreground_package=app.package,
                    attempts=attempt,
                    elapsed=time.monotonic() - start,
                    error=None,
                )
            last_error = (
                f"{app.package!r} did not reach the foreground within "
                f"{app.launch_timeout}s (attempt {attempt}/{total_attempts})"
            )
            self._logger.warning(
                "application_manager.launch_attempt_failed",
                device=device_id,
                package=app.package,
                attempt=attempt,
            )

        return LaunchResult(
            success=False,
            package=app.package,
            foreground_package=await self.foreground_package(device_id),
            attempts=total_attempts,
            elapsed=time.monotonic() - start,
            error=last_error,
        )

    async def stop(self, device_id: str, package: str) -> None:
        """Force-stop *package* on *device_id*."""
        await self._device_manager.execute_shell(device_id, "am", "force-stop", package)
