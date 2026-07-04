"""Input manager: selects, connects, and orchestrates input providers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ugaf.core.config import Config
from ugaf.core.logger import Logger, get_logger
from ugaf.core.metrics import MetricsSnapshot, MetricsTracker
from ugaf.core.platform import detect_platform
from ugaf.input.exceptions import (
    ConnectionFailedError,
    CoordinateOutOfBoundsError,
    DeviceNotFoundError,
    InputError,
    ProviderNotAvailableError,
)
from ugaf.input.provider import InputProvider
from ugaf.input.registry import InputProviderRegistry
from ugaf.input.registry import registry as _default_registry
from ugaf.input.types import Button, Key

if TYPE_CHECKING:
    from ugaf.device.manager import DeviceManager

__all__ = [
    "InputManager",
]


def _validate_coordinates(
    x: int,
    y: int,
    screen_size: tuple[int, int] | None,
) -> None:
    """Validate screen coordinates.

    Args:
        x: Horizontal pixel position.
        y: Vertical pixel position.
        screen_size: Screen resolution ``(width, height)``, or
            ``None`` if unknown.

    Raises:
        CoordinateOutOfBoundsError: If the coordinates are outside the
            screen bounds.

    """
    if screen_size is not None:
        width, height = screen_size
        if x < 0 or x >= width or y < 0 or y >= height:
            raise CoordinateOutOfBoundsError(
                f"Coordinates ({x}, {y}) out of bounds for screen size ({width}x{height})"
            )


class InputManager:
    """Manages input providers with retry, throttling, and logging.

    One :class:`InputManager` targets exactly one input target (one
    Windows desktop, or one Android device). This is a deliberate
    design choice, not an oversight: driving multiple simultaneous
    Android devices means creating one :class:`InputManager` per
    device (typically one per :class:`~ugaf.platform.device.DeviceInfo`
    returned by :class:`~ugaf.device.manager.DeviceManager`), not
    making a single manager multi-device-aware internally. This keeps
    per-device state (screen size, connection status, retry state)
    trivially isolated and lets a future multi-device orchestrator
    just hold a dict of ``{device_id: InputManager}`` without any
    change to this class.

    Usage::

        mgr = InputManager(config)
        mgr.connect()
        mgr.click(100, 200)
        mgr.type_text("hello")
        mgr.disconnect()

    Targeting a specific device explicitly (overriding config, useful
    when driving multiple devices from one process)::

        mgr = InputManager(config, device_id="emulator-5554", device_manager=dm)
        mgr.connect()

    Or as a context manager::

        async with InputManager(config) as mgr:
            mgr.click(100, 200)
    """

    def __init__(
        self,
        config: Config,
        registry: InputProviderRegistry | None = None,
        device_id: str | None = None,
        device_manager: DeviceManager | None = None,
    ) -> None:
        """Initialize the input manager from application configuration.

        Args:
            config: Framework configuration object.
            registry: Optional provider registry.  Defaults to the
                global :data:`~ugaf.input.registry.registry` singleton.
            device_id: Optional explicit target device serial,
                overriding ``input.adb.default_device``. Set this to
                run multiple ``InputManager`` instances against
                different devices from a single shared ``Config``.
            device_manager: Optional :class:`~ugaf.device.manager.DeviceManager`.
                When provided and the ADB provider is selected,
                ``connect()`` checks the device's real status
                (online/offline/unauthorized) through it before
                attempting to connect, giving a precise error instead
                of ``AdbInputProvider``'s own narrower "not found"
                check. Optional and decoupled: ``ugaf.input`` does not
                require ``ugaf.device`` to function standalone.

        """
        self._config = config
        self._registry = registry or _default_registry
        self._provider: InputProvider | None = None
        self._logger: Logger = get_logger()
        self._dry_run: bool = bool(config.get("input.dry_run", False))
        self._retry_count: int = int(config.get("input.retry.count", 3))
        self._retry_delay: float = float(config.get("input.retry.delay", 0.5))
        self._verbose: bool = bool(config.get("input.verbose", False))
        self._screen_size: tuple[int, int] | None = None
        self._device_id = device_id
        self._device_manager = device_manager
        self._metrics = MetricsTracker()

    @property
    def provider(self) -> InputProvider | None:
        """Return the current input provider."""
        return self._provider

    @property
    def screen_size(self) -> tuple[int, int] | None:
        """Return the detected screen resolution."""
        return self._screen_size

    @property
    def metrics(self) -> MetricsSnapshot:
        """Return input latency metrics (rolling window) for this device/target.

        Measures wall-clock time for each provider call (click, drag,
        type_text, ...) — the round trip of actually injecting the
        input, not just the Python call overhead.
        """
        return self._metrics.snapshot()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Select and connect the input provider.

        Reads ``input.provider`` from the application configuration
        to determine which provider to instantiate.

        Raises:
            ProviderNotAvailableError: If the requested provider is unknown.
            ConnectionFailedError: If connecting fails after all retries.

        """
        configured = self._config.get("input.provider")
        provider_name = str(configured) if configured is not None else self._default_provider_name()
        self._logger.info(
            "input.connecting",
            provider=provider_name,
        )

        if provider_name == "adb":
            self._check_device_status_via_manager()

        provider_config = self._build_provider_config()
        try:
            self._provider = self._registry.create(provider_name, provider_config)
        except KeyError as exc:
            raise ProviderNotAvailableError(f"Unknown input provider: {provider_name!r}") from exc

        last_exc: Exception | None = None
        for attempt in range(1, self._retry_count + 1):
            try:
                self._provider.connect()
            except InputError as exc:
                self._logger.warning(
                    "input.connect_attempt_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                last_exc = exc
                if attempt < self._retry_count:
                    time.sleep(self._retry_delay)
                continue
            else:
                self._detect_screen_size()
                self._logger.info(
                    "input.connected",
                    provider=provider_name,
                    screen_size=self._screen_size,
                )
                return

        msg = f"Failed to connect to {provider_name!r} provider after {self._retry_count} attempts"
        raise ConnectionFailedError(msg) from last_exc

    def disconnect(self) -> None:
        """Disconnect the current provider."""
        if self._provider is not None:
            self._provider.disconnect()
            self._logger.info("input.disconnected")
            self._provider = None

    def __enter__(self) -> InputManager:
        """Enter context: connect and return self."""
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        """Exit context: disconnect."""
        self.disconnect()

    # ------------------------------------------------------------------
    # Mouse / touch
    # ------------------------------------------------------------------

    def click(self, x: int, y: int, button: Button = "left") -> None:
        """Click at screen coordinates.

        Raises:
            CoordinateOutOfBoundsError: If the coordinates are outside
                the detected screen bounds.

        """
        self._check_coordinates(x, y)
        self._with_provider(lambda p: p.click(x, y, button=button))

    def double_click(self, x: int, y: int) -> None:
        """Double-click at screen coordinates.

        Raises:
            CoordinateOutOfBoundsError: If the coordinates are outside
                the detected screen bounds.

        """
        self._check_coordinates(x, y)
        self._with_provider(lambda p: p.double_click(x, y))

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screen coordinates.

        Raises:
            CoordinateOutOfBoundsError: If the coordinates are outside
                the detected screen bounds.

        """
        self._check_coordinates(x, y)
        self._with_provider(lambda p: p.right_click(x, y))

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move the mouse pointer.

        Raises:
            CoordinateOutOfBoundsError: If the coordinates are outside
                the detected screen bounds.

        """
        self._check_coordinates(x, y)
        self._with_provider(lambda p: p.move_mouse(x, y, duration=duration))

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        """Drag from one coordinate to another.

        Raises:
            CoordinateOutOfBoundsError: If either coordinate is outside
                the detected screen bounds.

        """
        self._check_coordinates(x1, y1)
        self._check_coordinates(x2, y2)
        self._with_provider(
            lambda p: p.drag(x1, y1, x2, y2, duration=duration),
        )

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Scroll at the current or given position."""
        self._with_provider(lambda p: p.scroll(clicks, x=x, y=y))

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def key_down(self, key: Key) -> None:
        """Press and hold a key."""
        self._with_provider(lambda p: p.key_down(key))

    def key_up(self, key: Key) -> None:
        """Release a held key."""
        self._with_provider(lambda p: p.key_up(key))

    def press_key(self, key: Key) -> None:
        """Press and release a key."""
        self._with_provider(lambda p: p.press_key(key))

    def type_text(self, text: str) -> None:
        """Type a string of text."""
        self._with_provider(lambda p: p.type_text(text))

    def hotkey(self, *keys: Key) -> None:
        """Press a combination of keys simultaneously."""
        self._with_provider(lambda p: p.hotkey(*keys))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def wait(self, seconds: float) -> None:
        """Wait for the specified duration."""
        if self._provider is not None:
            self._provider.wait(seconds)
        else:
            time.sleep(seconds)

    def take_screenshot(self, path: str | None = None) -> bytes | None:
        """Capture a screenshot via the current provider."""
        return self._with_provider(  # type: ignore[no-any-return]
            lambda p: p.take_screenshot(path=path),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_provider_config(self) -> dict[str, Any]:
        """Build a provider-specific configuration dict from the application config.

        Extracts ADB executable, default device, and mouse delay from
        the application configuration.

        """
        cfg: dict[str, Any] = {}
        adb_exec = self._config.get("input.adb.executable")
        if adb_exec is not None:
            cfg["executable"] = str(adb_exec)
        default_device = self._target_device_id()
        if default_device is not None:
            cfg["default_device"] = default_device
        mouse_delay = self._config.get("input.delays.mouse")
        if mouse_delay is not None:
            cfg["mouse_delay"] = float(mouse_delay)
        return cfg

    def _target_device_id(self) -> str | None:
        """Return the effective target device serial.

        The explicit ``device_id`` constructor argument always wins
        over ``input.adb.default_device`` from config, so a caller
        driving multiple devices can share one ``Config`` object.
        """
        if self._device_id is not None:
            return self._device_id
        configured = self._config.get("input.adb.default_device")
        return str(configured) if configured is not None else None

    def _check_device_status_via_manager(self) -> None:
        """Best-effort pre-flight device status check via ``DeviceManager``.

        Only runs when a ``device_manager`` was supplied and a target
        device is known. Gives a precise, correctly-classified error
        (online/offline/unauthorized/unknown) instead of
        ``AdbInputProvider``'s own narrower "not found" check, without
        replacing that provider's own ``connect()`` logic.

        Raises:
            DeviceNotFoundError: If the device is known to
                ``device_manager`` but not currently ``ONLINE``.

        """
        if self._device_manager is None:
            return
        target = self._target_device_id()
        if target is None:
            return

        from ugaf.platform.device import DeviceStatus

        device = self._device_manager.get_device(target)
        if device is None:
            devices = self._device_manager.discover()
            device = next((d for d in devices if d.id == target), None)
        if device is not None and device.status is not DeviceStatus.ONLINE:
            raise DeviceNotFoundError(
                f"Device {target!r} is {device.status.value} (expected online)"
            )

    def _default_provider_name(self) -> str:
        """Choose a provider when ``input.provider`` is not configured.

        Consults :func:`ugaf.core.platform.detect_platform` rather
        than hardcoding a single default: on Windows hosts, the
        Windows desktop provider is the natural default; on any other
        host (Linux, macOS, WSL) the only other built-in provider is
        the ADB one, which matches this framework's primary use case
        of a non-Windows control machine driving an Android device.

        Returns:
            ``"windows"`` on Windows, otherwise ``"adb"``.

        """
        return "windows" if detect_platform().is_windows else "adb"

    def _detect_screen_size(self) -> None:
        """Try to detect the screen size from the connected provider."""
        try:
            if hasattr(self._provider, "screen_size"):
                self._screen_size = self._provider.screen_size  # type: ignore[union-attr]
        except Exception:
            self._screen_size = None

    def _check_coordinates(self, x: int, y: int) -> None:
        """Validate screen coordinates before delegating."""
        _validate_coordinates(x, y, self._screen_size)

    def _log_input(self, action: str, **kwargs: Any) -> None:
        """Log an input action (only in verbose mode)."""
        if self._verbose:
            self._logger.info(f"input.{action}", **kwargs)

    def _with_provider(self, action: Any) -> Any:
        """Execute an action on the provider.

        Handles logging, dry-run, and error propagation.
        """
        if self._provider is None:
            raise ConnectionFailedError("InputManager is not connected")
        if self._dry_run:
            self._logger.info("input.dry_run", action=str(action))
            return None
        with self._metrics.measure():
            return action(self._provider)
