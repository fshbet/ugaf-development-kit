r"""ADB-backed screenshot provider.

Uses ``adb exec-out screencap -p`` rather than the older
``adb shell screencap -p`` + ``adb pull`` two-step: ``exec-out`` avoids
the pseudo-terminal that corrupts binary PNG data (turning ``\n`` into
``\r\n``) and streams directly to the host without an intermediate
write to device storage. See ``SCREENSHOT_CAPTURE_STRATEGY.md`` for the
full comparison against scrcpy, MediaProjection, UI Automator, and
minicap.
"""

from __future__ import annotations

import subprocess

from ugaf.device.adb_provider import AdbDeviceProvider
from ugaf.imaging.exceptions import ImageLoadError
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.platform.device import DeviceStatus
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

__all__ = [
    "AdbScreenshotProvider",
]


class AdbScreenshotProvider(ScreenshotProvider):
    """Screenshot provider for a single Android device via ADB.

    Scoped to one device per instance, mirroring
    :class:`~ugaf.input.adb.AdbInputProvider`'s per-device design
    (ADR-011) — driving screenshots for multiple devices means holding
    multiple :class:`AdbScreenshotProvider` instances, not making this
    class internally multi-device-aware.
    """

    def __init__(
        self,
        imaging: ImagingManager,
        device_id: str | None = None,
        executable: str = "adb",
        device_provider: AdbDeviceProvider | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the ADB screenshot provider.

        Args:
            imaging: Used to decode the captured PNG bytes into an
                :class:`~ugaf.imaging.image.Image`.
            device_id: Target device serial. If ``None``, the first
                online device is used at capture time.
            executable: Path to the ``adb`` binary.
            device_provider: Optional :class:`AdbDeviceProvider` to
                reuse (e.g. one already owned by a
                :class:`~ugaf.device.manager.DeviceManager`) instead of
                constructing a new one.
            timeout: Timeout in seconds for the capture subprocess.

        """
        self._imaging = imaging
        self._device_id = device_id
        self._executable = executable
        self._device_provider = device_provider or AdbDeviceProvider(executable=executable)
        self._timeout = timeout

    def capture_full(self) -> Image:
        """Capture the entire device screen via ``adb exec-out screencap -p``.

        Raises:
            ScreenshotError: If no online device is available, the
                capture command fails, or the PNG cannot be decoded.

        """
        device_id = self._resolve_device_id()
        try:
            result = subprocess.run(
                [self._executable, "-s", device_id, "exec-out", "screencap", "-p"],
                capture_output=True,
                timeout=self._timeout,
            )
        except FileNotFoundError as exc:
            raise ScreenshotError(f"adb executable not found: {self._executable!r}") from exc
        except subprocess.TimeoutExpired as exc:
            raise ScreenshotError(f"Screenshot capture timed out after {self._timeout}s") from exc

        if result.returncode != 0 or not result.stdout:
            stderr = result.stderr.decode("utf-8", errors="replace").strip()
            raise ScreenshotError(f"screencap failed (exit {result.returncode}): {stderr}")

        try:
            return self._imaging.from_bytes(result.stdout)
        except ImageLoadError as exc:
            raise ScreenshotError(f"Failed to decode captured screenshot: {exc}") from exc

    def capture_region(self, region: Region) -> Image:
        """Capture the full screen and crop to *region*.

        ADB has no server-side partial-capture API, so this always
        transfers a full frame — for high-frequency region-only
        capture, a streaming provider (e.g. a future
        ``ScrcpyScreenshotProvider``) is a better fit. See
        ``SCREENSHOT_CAPTURE_STRATEGY.md``.
        """
        full = self.capture_full()
        return full.crop(region.x, region.y, region.width, region.height)

    def capture_game_window(self, window_title: str) -> Image:
        """Not supported: Android has no concept of a titled desktop window.

        Raises:
            ScreenshotError: Always.

        """
        raise ScreenshotError(
            "capture_game_window is not supported by AdbScreenshotProvider "
            "(Android has no window titles); use capture_full() or capture_region()"
        )

    def _resolve_device_id(self) -> str:
        """Return the configured device, or the first online device found.

        Raises:
            ScreenshotError: If no online device is available.

        """
        if self._device_id is not None:
            return self._device_id
        devices = self._device_provider.list_devices()
        online = [d for d in devices if d.status is DeviceStatus.ONLINE]
        if not online:
            raise ScreenshotError("No online Android devices available for screenshot capture")
        return online[0].id
