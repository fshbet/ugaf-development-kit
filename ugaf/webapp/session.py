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
from collections import deque
from pathlib import Path
from typing import Any

from ugaf.apps.types import AppDefinition
from ugaf.core.bootstrap import Application
from ugaf.core.config import Config
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.input.manager import InputManager
from ugaf.platform.device import DeviceInfo
from ugaf.sdk.state import GameState
from ugaf.vision.adb_screenshot import AdbScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager

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

    def connect_device(self, device_id: str) -> None:
        """Create and connect an InputManager + ScreenshotManager for *device_id*.

        A no-op if already connected. Every device the UI connects to
        is an Android device reached over ADB — this always selects
        the ``adb`` input provider rather than trusting the shared
        framework config's ``input.provider`` (which defaults to
        ``windows``, meant for desktop input automation in a
        different context).
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
        screenshot.connect_with(AdbScreenshotProvider(self._imaging, device_id=device_id))

        self._connections[device_id] = DeviceConnection(device_id, input_manager, screenshot)

    def disconnect_device(self, device_id: str) -> None:
        """Disconnect and forget *device_id*'s connection, if any."""
        connection = self._connections.pop(device_id, None)
        if connection is not None:
            connection.input_manager.disconnect()

    def _require_connection(self, device_id: str) -> DeviceConnection:
        if device_id not in self._connections:
            raise KeyError(f"Device {device_id!r} is not connected")
        return self._connections[device_id]

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

    async def run_plugin(self, plugin_id: str) -> None:
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

        Raises:
            GameSDKError: If *plugin_id* is unknown, or in a terminal
                state (``SHUTDOWN``/``ERROR``) that cannot be resumed.

        """
        assert self.app.plugin_manager is not None
        manager = self.app.plugin_manager
        lifecycle = manager.lifecycles.get(plugin_id)

        if lifecycle is None or lifecycle.state is GameState.CREATED:
            await manager.initialize(plugin_id)
            await manager.start(plugin_id)
        elif lifecycle.state is GameState.RUNNING:
            return
        elif lifecycle.state is GameState.INITIALIZED:
            await manager.start(plugin_id)
        elif lifecycle.state is GameState.PAUSED:
            await manager.resume(plugin_id)
        elif lifecycle.state is GameState.STOPPED:
            await manager.start(plugin_id)
        else:
            # ERROR or SHUTDOWN: let start() raise the real error.
            await manager.start(plugin_id)

    async def stop_plugin(self, plugin_id: str) -> None:
        """Stop a plugin if it is currently running or paused; a no-op otherwise."""
        assert self.app.plugin_manager is not None
        manager = self.app.plugin_manager
        lifecycle = manager.lifecycles.get(plugin_id)
        if lifecycle is None or lifecycle.state not in (GameState.RUNNING, GameState.PAUSED):
            return
        await manager.stop(plugin_id)

    async def plugin_health(self, plugin_id: str) -> dict[str, Any]:
        """Return a single plugin's health/status dict."""
        assert self.app.plugin_manager is not None
        return await self.app.plugin_manager.health(plugin_id)
