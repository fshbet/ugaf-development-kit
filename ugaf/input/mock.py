"""No-op input provider that logs every action instead of performing it.

Useful for running plugins and demos without real hardware — the same
role :class:`~ugaf.vision.mock_screenshot.MockScreenshotProvider` plays
for screenshots.
"""

from __future__ import annotations

from typing import Any

from ugaf.core.logger import Logger, get_logger
from ugaf.input.provider import InputProvider
from ugaf.input.types import Button, Key

__all__ = [
    "MockInputProvider",
]


class MockInputProvider(InputProvider):
    """Input provider that logs actions and records call history instead of acting.

    ``screen_size`` defaults to ``(1080, 1920)`` (overridable via the
    ``screen_width``/``screen_height`` config keys) so coordinate
    validation in :class:`~ugaf.input.manager.InputManager` behaves the
    same as it would against a real device.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the mock provider.

        Args:
            config: Optional dict with ``screen_width``/``screen_height``.

        """
        self._config = config or {}
        self._connected = False
        self._logger: Logger = get_logger()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def connect(self) -> None:
        """Mark the provider as connected."""
        self._connected = True
        self._logger.info("input.mock_connected")

    def disconnect(self) -> None:
        """Mark the provider as disconnected."""
        self._connected = False

    def is_connected(self) -> bool:
        """Return whether the provider is connected."""
        return self._connected

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return the configured (or default) screen resolution."""
        return (
            int(self._config.get("screen_width", 1080)),
            int(self._config.get("screen_height", 1920)),
        )

    def _record(self, action: str, *args: Any) -> None:
        self.calls.append((action, args))
        self._logger.info(f"input.mock_{action}", args=args)

    def click(self, x: int, y: int, button: Button = "left") -> None:
        """Log a click instead of performing one."""
        self._record("click", x, y, button)

    def double_click(self, x: int, y: int) -> None:
        """Log a double-click instead of performing one."""
        self._record("double_click", x, y)

    def right_click(self, x: int, y: int) -> None:
        """Log a right-click instead of performing one."""
        self._record("right_click", x, y)

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        """Log a mouse move instead of performing one."""
        self._record("move_mouse", x, y, duration)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        """Log a drag/swipe instead of performing one."""
        self._record("drag", x1, y1, x2, y2, duration)

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Log a scroll instead of performing one."""
        self._record("scroll", clicks, x, y)

    def key_down(self, key: Key) -> None:
        """Log a key-down instead of performing one."""
        self._record("key_down", key)

    def key_up(self, key: Key) -> None:
        """Log a key-up instead of performing one."""
        self._record("key_up", key)

    def press_key(self, key: Key) -> None:
        """Log a key press instead of performing one."""
        self._record("press_key", key)

    def type_text(self, text: str) -> None:
        """Log a type_text instead of performing one."""
        self._record("type_text", text)

    def hotkey(self, *keys: Key) -> None:
        """Log a hotkey instead of performing one."""
        self._record("hotkey", *keys)

    def wait(self, seconds: float) -> None:
        """Log a wait instead of sleeping (demos/tests should stay fast)."""
        self._record("wait", seconds)

    def take_screenshot(self, path: str | None = None) -> bytes | None:
        """Log a screenshot request; returns ``None`` (use a ScreenshotProvider instead)."""
        self._record("take_screenshot", path)
        return None
