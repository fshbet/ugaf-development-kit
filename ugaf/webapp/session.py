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

from ugaf.android_platform import AndroidPlatformManager
from ugaf.apps.types import AppDefinition
from ugaf.core.bootstrap import Application
from ugaf.core.config import Config
from ugaf.core.logger import get_logger
from ugaf.device.lifecycle import DeviceLifecycle, DeviceState
from ugaf.emulator import (
    EmulatorBootTimeoutError,
    EmulatorManager,
    EmulatorManagerError,
    EnvironmentChecker,
)
from ugaf.emulator.boot_diagnostics import BootMonitor
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.input.manager import InputManager
from ugaf.platform.device import DeviceInfo, DeviceStatus
from ugaf.sdk.state import GameState
from ugaf.vision.adb_screenshot import AdbScreenshotProvider
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.screenshot import ScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager
from ugaf.vision.window_capture import WindowCaptureProvider

_DEFAULT_GAMES_DIR = Path("games")

# Owner tag recorded on every DeviceLifecycle transition inside the
# device-connect boot sequence (ADR-023's logging requirement: every
# transition must be attributable to the component that drove it).
_BOOT_OWNER = "AppSession.connect_device"

__all__ = [
    "AppSession",
    "DeviceConnection",
    "DeviceRecoveryError",
]


class DeviceRecoveryError(Exception):
    """Raised when a device cannot be brought to ``READY`` via the boot-sequence pipeline.

    Carries the pipeline *stage* that failed so API/UI callers can
    show a precise diagnostic instead of a bare "not connected".
    """

    def __init__(self, device_id: str, stage: str, reason: str) -> None:
        """Record which pipeline stage failed and why."""
        super().__init__(reason)
        self.device_id = device_id
        self.stage = stage
        self.reason = reason


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
        self._connect_options: dict[str, tuple[str, str | None]] = {}
        self._lifecycle = DeviceLifecycle()
        self._imaging = ImagingManager()
        self.log_buffer: deque[dict[str, Any]] = deque(maxlen=log_buffer_size)
        self._log_handler = _LogBufferHandler(self.log_buffer)
        self._emulator_manager: EmulatorManager | None = None
        self._platform_manager: AndroidPlatformManager | None = None
        self._boot_monitor = BootMonitor()

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
        """Return whether *device_id* is authoritatively ``READY``.

        Backed entirely by :class:`~ugaf.device.lifecycle.DeviceLifecycle`
        (ADR-020) — there is no independent "connected" flag anymore,
        so this can never disagree with :meth:`device_state`.
        """
        return self._lifecycle.is_ready(device_id)

    def device_state(self, device_id: str) -> str:
        """Return the single authoritative lifecycle state for *device_id*."""
        return self._lifecycle.get(device_id).state.value

    def device_state_reason(self, device_id: str) -> str:
        """Return the human-readable reason for *device_id*'s current state."""
        return self._lifecycle.get(device_id).reason

    def boot_timeline(self, device_id: str) -> list[dict[str, Any]]:
        """Return *device_id*'s current-episode lifecycle transition history.

        Powers the webapp's Boot Timeline panel: every transition since
        the current connect/boot attempt began, each attributed to the
        component that drove it and timestamped with elapsed time --
        per ADR-023's logging requirement that any failure be
        reproducible from the transition history alone.
        """
        return [
            {
                "state": snapshot.state.value,
                "reason": snapshot.reason,
                "owner": snapshot.owner,
                "elapsed_seconds": snapshot.elapsed_seconds,
                "updated_at": snapshot.updated_at,
            }
            for snapshot in self._lifecycle.history(device_id)
        ]

    def connect_device(
        self,
        device_id: str,
        capture_provider: str = "adb",
        window_title: str | None = None,
    ) -> None:
        """Run the full boot-sequence pipeline and bring *device_id* to ``READY``.

        A no-op if already ``READY``. Input always goes over ADB
        (input injection, device control, and app lifecycle stay on
        ADB per ``ARCHITECTURE.md``) rather than trusting the shared
        framework config's ``input.provider`` (which defaults to
        ``windows``, meant for desktop input automation in a
        different context) — only the *frame source* is selectable.

        Per ADR-020, "connected" is no longer declared the instant
        objects are constructed: the device must actually be reachable
        via ADB, finished booting, and produce a real test screenshot
        before the UI is told it is ``READY``.

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
            DeviceRecoveryError: If any stage of the boot sequence
                fails, naming the stage and the reason.

        """
        if self._lifecycle.is_ready(device_id) and device_id in self._connections:
            return
        self._connect_options[device_id] = (capture_provider, window_title)
        self._run_boot_sequence(device_id, capture_provider, window_title)

    def _run_boot_sequence(
        self, device_id: str, capture_provider: str, window_title: str | None
    ) -> None:
        """Execute the documented boot sequence, transitioning through every state.

        Launch Emulator (already done by the caller, e.g. Start AVD) ->
        Wait for emulator process (implied by ADB visibility) ->
        ``adb wait-for-device`` (WAITING_FOR_ADB) ->
        ``sys.boot_completed == 1`` + launcher visible + unlock screen (BOOTING) ->
        Initialize Screenshot Provider (INITIALIZING) ->
        Capture test screenshot (CAPTURING_TEST_FRAME) ->
        Test tap injection (TESTING_INPUT) ->
        Mark Device Ready (READY).

        Any existing partial connection is torn down before retrying,
        so recovery attempts never leak stale managers.

        Raises:
            ScreenshotError: If *capture_provider*/*window_title* are
                invalid — a client request-validation error, distinct
                from a pipeline/recovery failure, so it is not wrapped
                as a :class:`DeviceRecoveryError`.

        """
        # Validate the request shape before touching the lifecycle at all:
        # an unknown capture_provider or a missing window_title is a bad
        # request, not a device that failed to recover.
        capture = self._build_capture_provider(device_id, capture_provider, window_title)

        lifecycle = self._lifecycle
        stale = self._connections.pop(device_id, None)
        if stale is not None:
            stale.input_manager.disconnect()

        lifecycle.transition(
            device_id, DeviceState.STARTING, "connect/recovery requested", owner=_BOOT_OWNER
        )

        assert self.app.device_manager is not None
        lifecycle.transition(
            device_id, DeviceState.WAITING_FOR_ADB, "checking ADB reachability", owner=_BOOT_OWNER
        )
        device = next((d for d in self.app.device_manager.discover() if d.id == device_id), None)
        if device is None:
            lifecycle.transition(
                device_id, DeviceState.ERROR, "device not found by ADB", owner=_BOOT_OWNER
            )
            raise DeviceRecoveryError(
                device_id, "waiting_for_adb", f"Device {device_id!r} not found by ADB"
            )
        if device.status is not DeviceStatus.ONLINE:
            reason = f"device is {device.status.value} (expected online)"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "waiting_for_adb", reason.capitalize())

        lifecycle.transition(
            device_id, DeviceState.BOOTING, "verifying boot completion", owner=_BOOT_OWNER
        )
        try:
            booted = self._is_boot_completed(device_id)
        except Exception as exc:  # noqa: BLE001 - surfaced as a diagnostic, not raised raw
            reason = f"could not query boot state: {exc}"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "booting", reason) from exc
        if not booted:
            reason = "sys.boot_completed != 1"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "booting", "Device has not finished booting")
        self._unlock_screen(device_id)

        lifecycle.transition(
            device_id,
            DeviceState.INITIALIZING,
            "starting input/screenshot providers",
            owner=_BOOT_OWNER,
        )
        adb_config = Config.from_dict({"input": {"provider": "adb"}})
        input_manager = InputManager(
            adb_config,
            device_id=device_id,
            device_manager=self.app.device_manager,
        )
        try:
            input_manager.connect()
            screenshot = ScreenshotManager(imaging=self._imaging)
            screenshot.connect_with(capture)
        except Exception as exc:
            reason = f"provider initialization failed: {exc}"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "initializing", reason) from exc

        lifecycle.transition(
            device_id,
            DeviceState.CAPTURING_TEST_FRAME,
            "capturing test screenshot",
            owner=_BOOT_OWNER,
        )
        try:
            screenshot.capture_full()
        except Exception as exc:
            input_manager.disconnect()
            reason = f"test screenshot failed: {exc}"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "capturing_test_frame", reason) from exc

        lifecycle.transition(
            device_id, DeviceState.TESTING_INPUT, "testing tap injection", owner=_BOOT_OWNER
        )
        try:
            input_manager.click(1, 1)
        except Exception as exc:
            input_manager.disconnect()
            reason = f"test tap failed: {exc}"
            lifecycle.transition(device_id, DeviceState.ERROR, reason, owner=_BOOT_OWNER)
            raise DeviceRecoveryError(device_id, "testing_input", reason) from exc

        self._connections[device_id] = DeviceConnection(device_id, input_manager, screenshot)
        lifecycle.transition(
            device_id, DeviceState.READY, "boot sequence complete", owner=_BOOT_OWNER
        )

    def _unlock_screen(self, device_id: str) -> None:
        """Best-effort wake + dismiss the lock screen so automation isn't blocked by it.

        Sends ``KEYCODE_WAKEUP`` then ``KEYCODE_MENU`` -- dismisses a
        swipe-to-unlock (no PIN/pattern) lock screen, the default on a
        freshly created AVD. Never fatal: many devices have no lock
        screen active at all (already unlocked, or boot completed
        straight to the launcher), and PIN/pattern-protected lock
        screens can't be bypassed this way regardless -- this is a
        convenience for the common case, not a security bypass.
        """
        assert self.app.device_manager is not None
        try:
            self.app.device_manager.shell_sync(device_id, "input", "keyevent", "224")
            self.app.device_manager.shell_sync(device_id, "input", "keyevent", "82")
        except Exception as exc:  # noqa: BLE001 - unlocking is best-effort, never blocks boot
            get_logger().warning(
                "app_session.unlock_screen_failed", device=device_id, error=str(exc)
            )

    def _is_boot_completed(self, device_id: str) -> bool:
        """Check ``sys.boot_completed`` and launcher visibility over ADB."""
        assert self.app.device_manager is not None
        boot_prop = self.app.device_manager.shell_sync(device_id, "getprop", "sys.boot_completed")
        if boot_prop.strip() != "1":
            return False
        try:
            focus = self.app.device_manager.shell_sync(
                device_id, "dumpsys", "window", "|", "grep", "mCurrentFocus"
            )
        except Exception:  # noqa: BLE001 - launcher check is best-effort, boot_completed already confirmed
            return True
        return "Launcher" in focus or "launcher" in focus or focus.strip() != ""

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
        self._connect_options.pop(device_id, None)
        self._lifecycle.transition(
            device_id,
            DeviceState.DISCONNECTED,
            "disconnect requested",
            owner="AppSession.disconnect_device",
        )

    def _ensure_ready(self, device_id: str) -> DeviceConnection:
        """Return *device_id*'s connection, auto-recovering if lifecycle state is stale.

        Never fails purely because an internal flag is stale: if the
        device is not currently ``READY``, the full boot sequence is
        re-run once. Only a genuine pipeline failure (device
        unreachable, still booting, provider init/test-capture
        failure) results in an error — and that error names exactly
        which stage failed via :class:`DeviceRecoveryError`, per
        ADR-020's "revalidate, attempt recovery, only then report a
        diagnostic" requirement.
        """
        if self._lifecycle.is_ready(device_id) and device_id in self._connections:
            return self._connections[device_id]

        capture_provider, window_title = self._connect_options.get(device_id, ("adb", None))
        self._run_boot_sequence(device_id, capture_provider, window_title)
        return self._connections[device_id]

    def device_metrics(self, device_id: str) -> dict[str, Any]:
        """Return capture and input performance metrics for a connected device.

        Reports capture FPS/latency (whichever transport is active —
        ADB, window capture, or scrcpy, all measured the same way) and
        input latency, so the UI can compare transports on equal
        footing.
        """
        connection = self._ensure_ready(device_id)
        return {
            "capture": connection.screenshot.metrics.as_dict(),
            "input": connection.input_manager.metrics.as_dict(),
        }

    # ------------------------------------------------------------------
    # Screen / input actions
    # ------------------------------------------------------------------

    def capture(self, device_id: str) -> Image:
        """Capture the current screen for a connected device, auto-recovering first if needed."""
        return self._ensure_ready(device_id).screenshot.capture_full()

    def encode_png(self, image: Image) -> bytes:
        """Encode a captured Image as PNG bytes for HTTP responses."""
        return self._imaging.backend.encode(image.data, fmt="png")

    def tap(self, device_id: str, x: int, y: int) -> None:
        """Tap coordinates on a connected device."""
        self._ensure_ready(device_id).input_manager.click(x, y)

    def swipe(self, device_id: str, x1: int, y1: int, x2: int, y2: int, duration: float) -> None:
        """Swipe/drag on a connected device."""
        self._ensure_ready(device_id).input_manager.drag(x1, y1, x2, y2, duration=duration)

    def type_text(self, device_id: str, text: str) -> None:
        """Type text on a connected device."""
        self._ensure_ready(device_id).input_manager.type_text(text)

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

    def _get_platform_manager(self) -> AndroidPlatformManager:
        """Lazily build the :class:`~ugaf.android_platform.AndroidPlatformManager`.

        Wraps whatever :meth:`_get_emulator_manager` currently holds
        (so it shares the exact same success/failure caching behavior)
        together with the shared :class:`DeviceLifecycle` -- see
        ADR-021. Rebuilt each call since it's a cheap facade over
        already-cached managers; only ``_emulator_manager`` itself is
        the expensive-to-construct part.
        """
        assert self.app.device_manager is not None
        return AndroidPlatformManager(
            self._get_emulator_manager(),
            self.app.device_manager,
            self._lifecycle,
            environment_checker=EnvironmentChecker(),
        )

    def emulator_status(self) -> dict[str, Any]:
        """Return the live Android Platform "Environment Doctor" report, never cached.

        Always re-probes the real environment (see
        :class:`~ugaf.emulator.dependencies.EnvironmentChecker`) instead
        of reusing a previous result, so a status that was true a
        minute ago (e.g. "Android Studio not found") cannot linger after
        the real state changes. Physical/virtual device counts come
        straight from :class:`~ugaf.device.manager.DeviceManager` --
        the same single source of truth ``/api/devices`` uses -- never a
        second, independent device count.
        """
        report = EnvironmentChecker().check()
        dependencies = [
            {
                "name": s.name,
                "found": s.found,
                "path": s.path,
                "detail": s.detail,
                "version": s.version,
            }
            for s in report.as_list()
        ]
        blocking = report.first_missing()
        assert self.app.device_manager is not None
        devices = self.app.device_manager.discover()
        virtual_count = sum(1 for d in devices if d.id.startswith("emulator-"))
        physical_count = len(devices) - virtual_count
        return {
            "available": report.ready,
            "sdk_root": report.sdk.path,
            "error": blocking.detail if blocking else None,
            "dependencies": dependencies,
            "physical_device_count": physical_count,
            "virtual_device_count": virtual_count,
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
        return {
            "name": avd.name,
            "valid": avd.valid,
            "error": avd.error,
            "display_name": avd.display_name,
        }

    def start_avd(self, name: str) -> dict[str, Any]:
        """Validate prerequisites and launch an AVD as a new emulator instance.

        Routed through :class:`~ugaf.android_platform.AndroidPlatformManager`
        so the ``VALIDATING`` -> ``STARTING`` lifecycle transitions are
        recorded on the same authoritative :class:`DeviceLifecycle` the
        device-connect pipeline uses (ADR-021) — never a second,
        independent notion of "starting".
        """
        handle = self._get_platform_manager().start_virtual_device(name)
        return {
            "name": handle.name,
            "adb_serial": handle.adb_serial,
            "console_port": handle.console_port,
            "adb_port": handle.adb_port,
        }

    def create_and_ready_avd(
        self,
        name: str,
        manufacturer: str,
        device_name: str,
        performance_profile: str = "mid_range",
        capture_provider: str = "adb",
        window_title: str | None = None,
    ) -> dict[str, Any]:
        """One-click Virtual Device: create -> validate -> boot -> connect -> READY.

        Per ADR-022, this is the single action the "Create Virtual
        Device" button performs — no intermediate manual Start/Connect
        clicks. Composes already-existing, independently-tested pieces
        rather than duplicating their logic:

        1. :meth:`~ugaf.android_platform.AndroidPlatformManager.create_virtual_device`
           (auto-sanitizes the name, auto-downloads the system image if
           missing).
        2. :meth:`~ugaf.android_platform.AndroidPlatformManager.start_virtual_device`
           (validates every blocking SDK dependency before launching).
        3. :class:`~ugaf.emulator.boot_diagnostics.BootMonitor` — per
           ADR-023, replaces a bare boolean "did it boot" check with a
           staged diagnostic identifying exactly which boot signal never
           arrived (emulator process, ADB visibility, boot-completion
           properties, boot animation, or launcher) if it doesn't.
        4. :meth:`connect_device` — the full ADR-020/ADR-022 boot-sequence
           pipeline (wait-for-ADB, boot-completion, screen unlock,
           provider init, test screenshot, test tap, ``READY``).

        Raises:
            EmulatorManagerError: If creation produces an invalid AVD.
            EmulatorBootTimeoutError: If the emulator does not reach a
                fully-booted state in time — carries the exact failed
                stage and full :class:`~ugaf.emulator.boot_diagnostics.BootDiagnostics`.
            DeviceRecoveryError: If any stage of the device-connect
                pipeline fails once ADB-reachable.

        """
        platform = self._get_platform_manager()
        avd = platform.create_virtual_device(name, manufacturer, device_name, performance_profile)
        if not avd.valid:
            raise EmulatorManagerError(f"Virtual Device creation failed: {avd.error}")

        # A "window" capture provider needs the emulator window's title,
        # which is always the (possibly sanitized) AVD name -- the caller
        # can't know that in advance for a brand-new AVD, so default it
        # here rather than requiring a second round-trip.
        if capture_provider == "window" and not window_title:
            window_title = avd.name

        handle = platform.start_virtual_device(avd.name)

        emulator_manager = self._get_emulator_manager()
        assert self.app.device_manager is not None
        diagnostics = self._boot_monitor.wait_for_boot(
            self.app.device_manager,
            emulator_manager,
            avd.name,
            handle.adb_serial,
            timeout=emulator_manager.boot_timeout,
        )
        if diagnostics.failed_stage is not None:
            raise EmulatorBootTimeoutError(
                f"Virtual Device {avd.name!r} did not finish booting: "
                f"stuck at stage {diagnostics.failed_stage!r} after "
                f"{diagnostics.elapsed_seconds:.0f}s. {diagnostics.recommended_action}",
                failed_stage=diagnostics.failed_stage,
                diagnostics=diagnostics,
            )

        self.connect_device(
            handle.adb_serial, capture_provider=capture_provider, window_title=window_title
        )

        return {
            "device_id": handle.adb_serial,
            "avd_name": avd.name,
            "display_name": avd.display_name,
            "state": self.device_state(handle.adb_serial),
        }

    def stop_avd(self, name: str) -> None:
        """Gracefully shut down a running AVD."""
        self._get_platform_manager().stop_virtual_device(name)

    def delete_avd(self, name: str) -> None:
        """Permanently delete an AVD."""
        self._get_platform_manager().delete_virtual_device(name)

    def rename_avd(self, name: str, new_name: str) -> None:
        """Rename an AVD."""
        self._get_emulator_manager().rename(name, new_name)
