"""ADB-backed device enumeration transport.

Implements :class:`ugaf.platform.device.DeviceProvider` using
``adb devices -l`` (not the narrower ``adb devices``) so that
``offline``, ``unauthorized``, and ``no permissions`` states are
captured explicitly instead of being silently indistinguishable from
"no device" — a real gap identified in the original repository audit
against :class:`ugaf.input.adb.AdbInputProvider`'s device parsing.

See ``ANDROID_TRANSPORT_STRATEGY.md`` for why ADB is the first
transport implemented here.
"""

from __future__ import annotations

import subprocess

from ugaf.device.exceptions import DeviceCommandError, TransportUnavailableError
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

__all__ = [
    "AdbDeviceProvider",
]

_STATE_MAP: dict[str, DeviceStatus] = {
    "device": DeviceStatus.ONLINE,
    "offline": DeviceStatus.OFFLINE,
    "unauthorized": DeviceStatus.UNAUTHORIZED,
}


class AdbDeviceProvider(DeviceProvider):
    """Enumerates Android devices visible to a local ``adb`` installation."""

    def __init__(self, executable: str = "adb", timeout: float = 10.0) -> None:
        """Initialize the ADB device provider.

        Args:
            executable: Path to the ``adb`` binary (defaults to
                relying on ``PATH``).
            timeout: Timeout in seconds for each ``adb`` invocation.

        """
        self._executable = executable
        self._timeout = timeout

    def list_devices(self) -> list[DeviceInfo]:
        """Return every device reported by ``adb devices -l``.

        Raises:
            TransportUnavailableError: If the ``adb`` binary cannot be
                found or executed.

        """
        result = self._run("devices", "-l")
        return self._parse_devices(result.stdout)

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Return a single device by serial, or ``None`` if not currently visible."""
        for device in self.list_devices():
            if device.id == device_id:
                return device
        return None

    def get_properties(self, device_id: str) -> dict[str, str]:
        """Return the full ``getprop`` dump for an online device.

        Args:
            device_id: The device serial.

        Returns:
            A dict of Android system property name to value. Empty if
            the device is not online or the command fails.

        """
        try:
            result = self._run("-s", device_id, "shell", "getprop")
        except (TransportUnavailableError, DeviceCommandError):
            return {}
        return self._parse_properties(result.stdout)

    def shell(self, device_id: str, *args: str) -> str:
        """Run an ``adb shell`` command on a specific device and return its stdout.

        Args:
            device_id: The device serial.
            *args: Shell command and arguments.

        Raises:
            TransportUnavailableError: If the ``adb`` binary cannot be
                found or executed.
            DeviceCommandError: If the command exits non-zero.

        """
        result = self._run("-s", device_id, "shell", *args)
        return result.stdout

    def restart_server(self) -> None:
        """Restart the local ADB server (``adb kill-server`` then ``adb start-server``).

        This is the documented recovery step for a device stuck in the
        ``offline`` state due to a hung ADB daemon.

        Raises:
            TransportUnavailableError: If the ``adb`` binary cannot be
                found or executed.

        """
        self._run("kill-server", check=False)
        self._run("start-server")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run an ``adb`` subcommand, translating failures into framework exceptions.

        Args:
            *args: Arguments to pass to the ``adb`` executable.
            check: If ``True``, a non-zero exit code raises
                :class:`DeviceCommandError`.

        Raises:
            TransportUnavailableError: If the ``adb`` binary is not
                installed/on PATH, or the call times out.
            DeviceCommandError: If *check* is ``True`` and the command
                exits non-zero.

        """
        try:
            result = subprocess.run(
                [self._executable, *args],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise TransportUnavailableError(
                f"adb executable not found: {self._executable!r}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TransportUnavailableError(f"adb command timed out: {args}") from exc

        if check and result.returncode != 0:
            raise DeviceCommandError(
                f"adb {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result

    @staticmethod
    def _parse_devices(output: str) -> list[DeviceInfo]:
        """Parse ``adb devices -l`` output into :class:`DeviceInfo` objects."""
        devices: list[DeviceInfo] = []
        for line in output.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]

            extra: dict[str, str] = {}
            for token in parts[2:]:
                if ":" in token:
                    key, _, value = token.partition(":")
                    extra[key] = value

            status = _STATE_MAP.get(state, DeviceStatus.UNKNOWN)
            if status is DeviceStatus.UNKNOWN:
                extra.setdefault("raw_state", state)

            devices.append(
                DeviceInfo(
                    id=serial,
                    name=extra.get("model", serial),
                    status=status,
                    platform="android",
                    transport="adb",
                    extra=extra,
                )
            )
        return devices

    @staticmethod
    def _parse_properties(output: str) -> dict[str, str]:
        """Parse ``adb shell getprop`` output (``[key]: [value]`` per line)."""
        properties: dict[str, str] = {}
        for line in output.strip().splitlines():
            if not line.startswith("["):
                continue
            try:
                key_part, value_part = line.split("]:", 1)
            except ValueError:
                continue
            key = key_part.strip().lstrip("[").rstrip("]")
            value = value_part.strip().lstrip("[").rstrip("]")
            properties[key] = value
        return properties
