"""Application session for the UGAF web UI.

Wraps a single :class:`~ugaf.core.bootstrap.Application` instance and
adds only what the UI needs beyond it: per-device
``InputManager``/``ScreenshotManager`` pairs (one per connected
device, per ADR-011), and an in-memory log ring buffer for the live
log panel. No new business logic — every action here is a thin
delegation to an existing manager.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from collections import deque
from pathlib import Path
from typing import Any

from ugaf.apps.types import AppDefinition
from ugaf.core.bootstrap import Application
from ugaf.core.config import Config
from ugaf.emulator import EmulatorManager, EnvironmentChecker
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.input.manager import InputManager
from ugaf.platform.device import DeviceInfo
from ugaf.sdk.state import GameState
from ugaf.vision.adb_screenshot import AdbScreenshotProvider
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.screenshot import ScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager
from ugaf.vision.window_capture import WindowCaptureProvider

_ANDROID_STUDIO_CANDIDATES = (
    r"%LOCALAPPDATA%\Programs\Android Studio\bin\studio64.exe",
    r"C:\Program Files\Android\Android Studio\bin\studio64.exe",
    r"C:\Program Files (x86)\Android\Android Studio\bin\studio64.exe",
)

_DEFAULT_GAMES_DIR = Path("games")

__all__ = [
    "AppSession",
    "DeviceConnection",
]


class _LogBufferHandler(logging.Handler):
    """Stdlib logging handler that appends formatted records to a bounded deque."""

    def __init__(self, buffer: deque[dict[str, Any]]) -> None:
        """Initialize the handler with the buffer it should append to."""
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        """Append a structured entry for *record* to the buffer."""
        self._buffer.append(
            {
                "timestamp": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
        )


class DeviceConnection:
    """Holds the per-device managers created for one connected device."""

    def __init__(
        self, device_id: str, input_manager: InputManager, screenshot: ScreenshotManager
    ) -> None:
        """Bind a device serial to its input and screenshot managers."""
        self.device_id = device_id
        self.input_manager = input_manager
        self.screenshot = screenshot


class AppSession:
    """Owns one Application instance plus the extra state the web UI needs.

    Usage::

        session = AppSession()
        await session.start()
        devices = session.list_devices()
        session.connect_device(devices[0].id)
        frame = session.capture(devices[0].id)
        await session.stop()

    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        games_dir: Path | str | None = None,
        log_buffer_size: int = 500,
    ) -> None:
        """Initialize the session (does not start anything yet).

        Args:
            config_path: Forwarded to :class:`Application`.
            games_dir: Forwarded to :class:`Application`.
            log_buffer_size: Maximum number of log entries kept for
                the live log panel.

        """
        self.app = Application(config_path=config_path, games_dir=games_dir)
        self._games_dir = Path(games_dir) if games_dir else _DEFAULT_GAMES_DIR
        self._connections: dict[str, DeviceConnection] = {}
        self._imaging = ImagingManager()
        self.log_buffer: deque[dict[str, Any]] = deque(maxlen=log_buffer_size)
        self._log_handler = _LogBufferHandler(self.log_buffer)
        self._emulator_manager: EmulatorManager | None = None

    async def start(self) -> None:
        """Initialize and start the underlying Application, and begin log capture.

        Plugins are discovered but *not* auto-started (unlike ``ugaf
        start`` on the CLI) — in the web control panel, the user
        starts a plugin explicitly via the "Run" button.
        """
        logging.getLogger().addHandler(self._log_handler)
        await self.app.initialize()
        await self.app.start(auto_start_plugins=False)

    async def stop(self) -> None:
        """Disconnect every device and stop the underlying Application."""
        for device_id in list(self._connections):
            self.disconnect_device(device_id)
        await self.app.stop()
        logging.getLogger().removeHandler(self._log_handler)

    # ------------------------------------------------------------------
    # Devices
    # ------------------------------------------------------------------

    def list_devices(self) -> list[DeviceInfo]:
        """Return the current device snapshot, re-discovering first."""
        assert self.app.device_manager is not None
        return self.app.device_manager.discover()

    def is_connected(self, device_id: str) -> bool:
        """Return whether *device_id* has an active session connection."""
        return device_id in self._connections

    def connect_device(
        self,
        device_id: str,
        capture_provider: str = "adb",
        window_title: str | None = None,
    ) -> None:
        """Create and connect an InputManager + ScreenshotManager for *device_id*.

        A no-op if already connected. Input always goes over ADB
        (input injection, device control, and app lifecycle stay on
        ADB per ``ARCHITECTURE.md``) rather than trusting the shared
        framework config's ``input.provider`` (which defaults to
        ``windows``, meant for desktop input automation in a
        different context) — only the *frame source* is selectable.

        Args:
            device_id: The device to connect to.
            capture_provider: Which capture transport to use for
                screenshots — ``"adb"`` (default, ``screencap`` over
                ADB), or ``"window"`` (capture an emulator's window
                directly; requires *window_title* and the optional
                ``pywin32``/``mss`` dependencies).
            window_title: Required when *capture_provider* is
                ``"window"`` — the target window's title (exact or
                substring match).

        Raises:
            ScreenshotError: If *capture_provider* is ``"window"`` and
                *window_title* is not given, or the capture transport
                itself is unavailable/misconfigured.

        """
        if device_id in self._connections:
            return

        adb_config = Config.from_dict({"input": {"provider": "adb"}})

        input_manager = InputManager(
            adb_config,
            device_id=device_id,
            device_manager=self.app.device_manager,
        )
        input_manager.connect()

        screenshot = ScreenshotManager(imaging=self._imaging)
        screenshot.connect_with(
            self._build_capture_provider(device_id, capture_provider, window_title)
        )

        self._connections[device_id] = DeviceConnection(device_id, input_manager, screenshot)

    def _build_capture_provider(
        self, device_id: str, capture_provider: str, window_title: str | None
    ) -> ScreenshotProvider:
        """Construct the requested capture transport for a new device connection."""
        if capture_provider == "adb":
            return AdbScreenshotProvider(self._imaging, device_id=device_id)
        if capture_provider == "window":
            if not window_title:
                raise ScreenshotError(
                    "capture_provider='window' requires a window_title "
                    "(the emulator window's title)"
                )
            return WindowCaptureProvider(self._imaging, window_title=window_title)
        raise ScreenshotError(f"Unknown capture_provider: {capture_provider!r}")

    def disconnect_device(self, device_id: str) -> None:
        """Disconnect and forget *device_id*'s connection, if any."""
        connection = self._connections.pop(device_id, None)
        if connection is not None:
            connection.input_manager.disconnect()

    def _require_connection(self, device_id: str) -> DeviceConnection:
        if device_id not in self._connections:
            raise KeyError(f"Device {device_id!r} is not connected")
        return self._connections[device_id]

    def device_metrics(self, device_id: str) -> dict[str, Any]:
        """Return capture and input performance metrics for a connected device.

        Reports capture FPS/latency (whichever transport is active —
        ADB, window capture, or scrcpy, all measured the same way) and
        input latency, so the UI can compare transports on equal
        footing.
        """
        connection = self._require_connection(device_id)
        return {
            "capture": connection.screenshot.metrics.as_dict(),
            "input": connection.input_manager.metrics.as_dict(),
        }

    # ------------------------------------------------------------------
    # Screen / input actions
    # ------------------------------------------------------------------

    def capture(self, device_id: str) -> Image:
        """Capture the current screen for a connected device."""
        return self._require_connection(device_id).screenshot.capture_full()

    def encode_png(self, image: Image) -> bytes:
        """Encode a captured Image as PNG bytes for HTTP responses."""
        return self._imaging.backend.encode(image.data, fmt="png")

    def tap(self, device_id: str, x: int, y: int) -> None:
        """Tap coordinates on a connected device."""
        self._require_connection(device_id).input_manager.click(x, y)

    def swipe(self, device_id: str, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        """Swipe/drag on a connected device."""
        self._require_connection(device_id).input_manager.drag(x1, y1, x2, y2, duration=duration)

    def type_text(self, device_id: str, text: str) -> None:
        """Type text on a connected device."""
        self._require_connection(device_id).input_manager.type_text(text)

    # ------------------------------------------------------------------
    # Automations (game/app plugins)
    # ------------------------------------------------------------------

    def list_plugins(self) -> list[dict[str, Any]]:
        """Return metadata for every registered automation as plain dicts (JSON-friendly).

        Uses the registry directly rather than ``discover()`` — plugins
        are already discovered once at ``Application.start()``, and
        ``discover()`` only returns *newly* found plugins on each call
        (duplicates of already-registered ones are silently skipped),
        so calling it again here would return an empty list once
        the app has started.

        Each entry includes ``target_app`` (name/package) when the
        automation declares one via ``app.yaml`` — ``None`` for
        automations with no target Android application (e.g. a
        desktop-only demo).
        """
        assert self.app.plugin_manager is not None
        metas = self.app.plugin_manager.registry.list()
        return [
            {
                "id": m.id,
                "name": m.name,
                "version": m.version,
                "author": m.author,
                "description": m.description,
                "capabilities": [c.value for c in m.capabilities],
                "target_app": self._target_app(m.id),
            }
            for m in metas
        ]

    def _target_app(self, plugin_id: str) -> dict[str, str] | None:
        """Return ``{"name": ..., "package": ...}`` for *plugin_id*'s ``app.yaml``, if any."""
        app_path = self._games_dir / plugin_id / "app.yaml"
        if not app_path.exists():
            return None
        app = AppDefinition.load(app_path)
        return {"name": app.name, "package": app.package}

    async def run_plugin(self, plugin_id: str, device_id: str | None = None) -> None:
        """Get a plugin running, regardless of its current lifecycle state.

        Idempotent and state-aware: a fresh plugin is
        initialized-then-started, an already-running plugin is a
        no-op, a paused one is resumed, and a stopped one is
        restarted — the UI's "Run" button should never fail just
        because it was clicked more than once.

        A plugin can also reach ``GameState.CREATED`` (registered but
        never initialized) before the user ever clicks "Run", as a
        side effect of ``plugin_health()`` calling ``load()`` — the
        automation list polls health to show live status. Treat that
        the same as "never touched": initialize, then start.

        Args:
            plugin_id: The automation to run.
            device_id: If given, runs a device-bound instance of this
                automation (see ``PluginManager``'s ``device_id``
                parameter) — letting the same automation run
                concurrently against several devices, each with
                independent state. ``None`` uses the single shared
                instance, as before.

        Raises:
            GameSDKError: If *plugin_id* is unknown, or in a terminal
                state (``SHUTDOWN``/``ERROR``) that cannot be resumed.

        """
        assert self.app.plugin_manager is not None
        manager = self.app.plugin_manager
        key = plugin_id if device_id is None else f"{plugin_id}@{device_id}"
        lifecycle = manager.lifecycles.get(key)

        if lifecycle is None or lifecycle.state is GameState.CREATED:
            await manager.initialize(plugin_id, device_id=device_id)
            await manager.start(plugin_id, device_id=device_id)
        elif lifecycle.state is GameState.RUNNING:
            return
        elif lifecycle.state is GameState.INITIALIZED:
            await manager.start(plugin_id, device_id=device_id)
        elif lifecycle.state is GameState.PAUSED:
            await manager.resume(plugin_id, device_id=device_id)
        elif lifecycle.state is GameState.STOPPED:
            await manager.start(plugin_id, device_id=device_id)
        else:
            # ERROR or SHUTDOWN: let start() raise the real error.
            await manager.start(plugin_id, device_id=device_id)

    async def stop_plugin(self, plugin_id: str, device_id: str | None = None) -> None:
        """Stop a plugin if it is currently running or paused; a no-op otherwise."""
        assert self.app.plugin_manager is not None
        manager = self.app.plugin_manager
        key = plugin_id if device_id is None else f"{plugin_id}@{device_id}"
        lifecycle = manager.lifecycles.get(key)
        if lifecycle is None or lifecycle.state not in (GameState.RUNNING, GameState.PAUSED):
            return
        await manager.stop(plugin_id, device_id=device_id)

    async def plugin_health(self, plugin_id: str, device_id: str | None = None) -> dict[str, Any]:
        """Return a single plugin's health/status dict."""
        assert self.app.plugin_manager is not None
        return await self.app.plugin_manager.health(plugin_id, device_id=device_id)

    # ------------------------------------------------------------------
    # Android Emulator (ugaf.emulator)
    # ------------------------------------------------------------------

    def _get_emulator_manager(self) -> EmulatorManager:
        """Lazily construct the :class:`~ugaf.emulator.EmulatorManager`.

        Construction shells out to locate the Android SDK, which some
        installs (or CI/test environments) may not have. A *successful*
        construction is cached (it's immutable once built), but a
        failed attempt is retried on every call rather than cached --
        caching a failure would mean the UI keeps reporting "SDK not
        found" forever even after the user fixes it (installs the SDK,
        sets ANDROID_HOME, etc.) without restarting the whole webapp, a
        real "stale status never re-validated" bug this project's ATDD
        process now explicitly guards against.

        Raises:
            SdkNotFoundError: If no Android SDK installation is found.

        """
        if self._emulator_manager is None:
            self._emulator_manager = EmulatorManager()
        return self._emulator_manager

    def emulator_status(self) -> dict[str, Any]:
        """Return live per-dependency status (Android Studio/SDK/tools), never cached.

        Always re-probes the real environment (see
        :class:`~ugaf.emulator.dependencies.EnvironmentChecker`) instead
        of reusing a previous result, so a status that was true a
        minute ago (e.g. "Android Studio not found") cannot linger after
        the real state changes.
        """
        report = EnvironmentChecker().check()
        dependencies = [
            {"name": s.name, "found": s.found, "path": s.path, "detail": s.detail}
            for s in report.as_list()
        ]
        blocking = report.first_missing()
        return {
            "available": report.ready,
            "sdk_root": report.sdk.path,
            "error": blocking.detail if blocking else None,
            "dependencies": dependencies,
        }

    def list_manufacturers(self) -> list[str]:
        """Return every supported device manufacturer."""
        return self._get_emulator_manager().list_manufacturers()

    def list_device_profiles(self, manufacturer: str) -> list[dict[str, Any]]:
        """Return every device profile for *manufacturer* as plain dicts."""
        profiles = self._get_emulator_manager().list_devices(manufacturer)
        return [
            {
                "device_name": p.device_name,
                "model": p.model,
                "android_version": p.android_version,
                "api_level": p.api_level,
            }
            for p in profiles
        ]

    def list_performance_profiles(self) -> list[str]:
        """Return every performance preset name."""
        return self._get_emulator_manager().list_performance_profiles()

    def list_android_versions(self) -> list[dict[str, Any]]:
        """Return every Android system image (installed or installable) as plain dicts."""
        images = self._get_emulator_manager().list_android_versions()
        return [
            {
                "api_level": img.api_level,
                "version_name": img.version_name,
                "tag": img.tag,
                "abi": img.abi,
                "installed": img.installed,
            }
            for img in images
        ]

    def check_system_image(self, manufacturer: str, device_name: str) -> dict[str, Any]:
        """Return whether the system image a device profile needs is already installed.

        Surfaced so the UI can show "Required system image installed:
        yes/no" before Create is clicked -- a first-time create for a
        not-yet-installed Android version will trigger an automatic
        (but potentially multi-minute) download.
        """
        installed = self._get_emulator_manager().check_system_image(manufacturer, device_name)
        return {"installed": installed}

    def list_avds(self) -> list[dict[str, Any]]:
        """Return every known AVD (valid or broken) as plain dicts."""
        avds = self._get_emulator_manager().list()
        return [
            {
                "name": a.name,
                "device": a.device,
                "target": a.target,
                "abi": a.abi,
                "valid": a.valid,
                "error": a.error,
                "running": a.running,
                "adb_serial": a.adb_serial,
            }
            for a in avds
        ]

    def create_avd(
        self, name: str, manufacturer: str, device_name: str, performance_profile: str
    ) -> dict[str, Any]:
        """Create a new AVD from a manufacturer/device profile and performance preset."""
        manager = self._get_emulator_manager()
        avd = manager.create(name, manufacturer, device_name, performance_profile)
        return {"name": avd.name, "valid": avd.valid, "error": avd.error}

    def start_avd(self, name: str) -> dict[str, Any]:
        """Launch an AVD as a new emulator instance."""
        handle = self._get_emulator_manager().start(name)
        return {
            "name": handle.name,
            "adb_serial": handle.adb_serial,
            "console_port": handle.console_port,
            "adb_port": handle.adb_port,
        }

    def stop_avd(self, name: str) -> None:
        """Gracefully shut down a running AVD."""
        self._get_emulator_manager().stop(name)

    def delete_avd(self, name: str) -> None:
        """Permanently delete an AVD."""
        self._get_emulator_manager().delete(name)

    def rename_avd(self, name: str, new_name: str) -> None:
        """Rename an AVD."""
        self._get_emulator_manager().rename(name, new_name)

    def open_android_studio(self) -> bool:
        """Best-effort launch of the Android Studio IDE, if found at a well-known path.

        Returns:
            ``True`` if a launch was attempted, ``False`` if Android
            Studio could not be located.

        """
        if sys.platform != "win32":
            found = shutil.which("studio") or shutil.which("android-studio")
            if not found:
                return False
            subprocess.Popen([found])
            return True

        for candidate in _ANDROID_STUDIO_CANDIDATES:
            path = Path(os.path.expandvars(candidate))
            if path.is_file():
                subprocess.Popen([str(path)])
                return True
        return False
