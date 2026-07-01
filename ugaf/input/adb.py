"""Android input provider using the Android Debug Bridge (ADB)."""

from __future__ import annotations

import re
import subprocess
import time
from typing import Any

from ugaf.input.exceptions import ConnectionFailedError, DeviceNotFoundError
from ugaf.input.provider import InputProvider
from ugaf.input.types import Button, Key

__all__ = [
    "AdbInputProvider",
]

# Common Android key codes for ``press_key`` / ``key_down`` / ``key_up``
_KEYCODE_MAP: dict[str, int] = {
    "home": 3,
    "back": 4,
    "call": 5,
    "endcall": 6,
    "0": 7,
    "1": 8,
    "2": 9,
    "3": 10,
    "4": 11,
    "5": 12,
    "6": 13,
    "7": 14,
    "8": 15,
    "9": 16,
    "star": 17,
    "pound": 18,
    "dpad_up": 19,
    "dpad_down": 20,
    "dpad_left": 21,
    "dpad_right": 22,
    "dpad_center": 23,
    "volume_up": 24,
    "volume_down": 25,
    "power": 26,
    "camera": 27,
    "clear": 28,
    "a": 29,
    "b": 30,
    "c": 31,
    "d": 32,
    "e": 33,
    "f": 34,
    "g": 35,
    "h": 36,
    "i": 37,
    "j": 38,
    "k": 39,
    "l": 40,
    "m": 41,
    "n": 42,
    "o": 43,
    "p": 44,
    "q": 45,
    "r": 46,
    "s": 47,
    "t": 48,
    "u": 49,
    "v": 50,
    "w": 51,
    "x": 52,
    "y": 53,
    "z": 54,
    "comma": 55,
    "period": 56,
    "alt_left": 57,
    "alt_right": 58,
    "shift_left": 59,
    "shift_right": 60,
    "tab": 61,
    "space": 62,
    "enter": 66,
    "del": 67,
    "delete": 67,
    "escape": 111,
    "menu": 82,
    "search": 84,
    "notification": 83,
    "app_switch": 187,
}


def _keycode(key: Key) -> int:
    """Convert a key name to an Android key code.

    Args:
        key: Key name (e.g. ``"home"``, ``"enter"``).

    Returns:
        The numeric Android key code.

    Raises:
        ValueError: If the key is not in the keycode map.

    """
    normalized = key.lower().replace(" ", "_")
    code = _KEYCODE_MAP.get(normalized)
    if code is None:
        if len(normalized) == 1:
            ordinal = ord(normalized.upper())
            if 65 <= ordinal <= 90:
                return ordinal - 65 + 29
        raise ValueError(f"Unknown Android key: {key!r}")
    return code


class AdbInputProvider(InputProvider):
    """Input provider for Android devices via ADB.

    Connects to a physical or emulated Android device over ADB and
    sends touch and key events through the ``input`` shell command.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the ADB input provider.

        Args:
            config: Provider configuration dict (``executable``,
                ``default_device``).

        """
        self._config = config or {}
        self._adb_path: str = self._config.get("executable", "adb")
        self._device_id: str | None = self._config.get("default_device")
        self._connected = False
        self._screen_width: int = 0
        self._screen_height: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to an Android device via ADB.

        Raises:
            ConnectionFailedError: If ADB is not available.
            DeviceNotFoundError: If no device is connected.

        """
        result = subprocess.run(
            [self._adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise ConnectionFailedError(
                f"ADB not available (exit code {result.returncode}): {result.stderr.strip()}"
            )

        devices = self._parse_devices(result.stdout)
        if not devices:
            raise DeviceNotFoundError("No Android devices connected")

        if self._device_id is not None:
            if self._device_id not in devices:
                raise DeviceNotFoundError(
                    f"Device {self._device_id!r} not found. Available: {devices}"
                )
        else:
            self._device_id = devices[0]

        self._detect_screen_size()
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect from the current device."""
        self._connected = False
        self._device_id = None

    def is_connected(self) -> bool:
        """Return whether the provider is connected to a device."""
        return self._connected

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return the device screen resolution as ``(width, height)``."""
        self._ensure_connected()
        return (self._screen_width, self._screen_height)

    @property
    def device_id(self) -> str | None:
        """Return the currently connected device ID."""
        return self._device_id

    def list_devices(self) -> list[str]:
        """List all connected Android devices.

        Returns:
            List of device serial numbers.

        Raises:
            ConnectionFailedError: If ADB is not available.

        """
        result = subprocess.run(
            [self._adb_path, "devices"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise ConnectionFailedError(f"ADB not available: {result.stderr.strip()}")
        return self._parse_devices(result.stdout)

    # ------------------------------------------------------------------
    # Mouse / touch
    # ------------------------------------------------------------------

    def click(self, x: int, y: int, button: Button = "left") -> None:
        """Tap at screen coordinates via ADB ``input tap``."""
        self._ensure_connected()
        self._adb_shell("input", "tap", str(x), str(y))

    def double_click(self, x: int, y: int) -> None:
        """Double-tap via two sequential taps."""
        self._ensure_connected()
        self.click(x, y)
        self.wait(0.05)
        self.click(x, y)

    def right_click(self, x: int, y: int) -> None:
        """Simulate a right-click via a long-press swipe."""
        self._ensure_connected()
        self._adb_shell(
            "input",
            "swipe",
            str(x),
            str(y),
            str(x),
            str(y),
            "500",
        )

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move pointer (simulated via short swipe on Android)."""
        self._ensure_connected()
        self._adb_shell(
            "input",
            "swipe",
            str(x),
            str(y),
            str(x + 1),
            str(y + 1),
            str(int(duration * 1000)),
        )

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        """Drag from one coordinate to another via ADB swipe."""
        self._ensure_connected()
        ms = max(1, int(duration * 1000))
        self._adb_shell(
            "input",
            "swipe",
            str(x1),
            str(y1),
            str(x2),
            str(y2),
            str(ms),
        )

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Scroll via ADB swipe at the current or given position."""
        self._ensure_connected()
        cx = x if x is not None else self._screen_width // 2
        cy = y if y is not None else self._screen_height // 2
        dy = int(clicks * 50)
        self._adb_shell(
            "input",
            "swipe",
            str(cx),
            str(cy),
            str(cx),
            str(cy + dy),
            "200",
        )

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def key_down(self, key: Key) -> None:
        """Press and hold a key via ADB keyevent."""
        code = _keycode(key)
        self._ensure_connected()
        self._adb_shell("input", "keyevent", str(code))

    def key_up(self, key: Key) -> None:
        """Release a held key (no-op on ADB; keydown fires keyevent)."""
        pass

    def press_key(self, key: Key) -> None:
        """Press and release a key via ADB keyevent."""
        code = _keycode(key)
        self._ensure_connected()
        self._adb_shell("input", "keyevent", str(code))

    def type_text(self, text: str) -> None:
        """Type text via the ADB ``input text`` command."""
        self._ensure_connected()
        escaped = text.replace(" ", "%s").replace("'", "")
        self._adb_shell("input", "text", escaped)

    def hotkey(self, *keys: Key) -> None:
        """Press multiple keys sequentially (ADB has no hotkey concept)."""
        for key in keys:
            self.press_key(key)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def wait(self, seconds: float) -> None:
        """Sleep for the specified duration."""
        time.sleep(seconds)

    def take_screenshot(self, path: str | None = None) -> bytes | None:
        """Capture a screenshot via ADB ``screencap``."""
        self._ensure_connected()
        assert self._device_id is not None
        result = subprocess.run(
            [self._adb_path, "-s", self._device_id, "exec-out", "screencap", "-p"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None
        if path is not None:
            with open(path, "wb") as fh:
                fh.write(result.stdout)
            return None
        return result.stdout

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectionFailedError("AdbInputProvider is not connected")

    def _adb_shell(self, *args: str) -> None:
        """Run an ADB shell command on the current device."""
        assert self._device_id is not None
        cmd = [self._adb_path, "-s", self._device_id, "shell", *args]
        subprocess.run(cmd, capture_output=True, timeout=30)

    def _detect_screen_size(self) -> None:
        """Detect the device screen resolution via ``wm size``."""
        assert self._device_id is not None
        result = subprocess.run(
            [self._adb_path, "-s", self._device_id, "shell", "wm", "size"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        match = re.search(r"(\d+)x(\d+)", result.stdout)
        if match:
            self._screen_width = int(match.group(1))
            self._screen_height = int(match.group(2))

    @staticmethod
    def _parse_devices(output: str) -> list[str]:
        """Parse the output of ``adb devices``.

        Args:
            output: Raw stdout from ``adb devices``.

        Returns:
            List of connected device serial numbers.

        """
        devices: list[str] = []
        for line in output.strip().splitlines():
            parts = line.split("\t")
            if len(parts) == 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices
