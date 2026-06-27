"""Windows input provider using pyautogui, keyboard, and mouse."""

from __future__ import annotations

import time
from typing import Any

from ugaf.input.exceptions import ConnectionFailedError
from ugaf.input.provider import InputProvider
from ugaf.input.types import Button, Key

__all__ = [
    "WindowsInputProvider",
]

_LIBRARIES_AVAILABLE: bool | None = None


def _check_libraries() -> bool:
    """Lazy-check whether the Windows automation libraries are installed.

    Returns:
        ``True`` if all three libraries are importable.

    """
    global _LIBRARIES_AVAILABLE  # noqa: PLW0603
    if _LIBRARIES_AVAILABLE is not None:
        return _LIBRARIES_AVAILABLE
    try:
        import keyboard  # noqa: F401
        import mouse  # noqa: F401
        import pyautogui  # noqa: F401
    except ImportError:
        _LIBRARIES_AVAILABLE = False
    else:
        _LIBRARIES_AVAILABLE = True
    return _LIBRARIES_AVAILABLE


class WindowsInputProvider(InputProvider):
    """Input provider for the Windows desktop.

    Uses ``pyautogui`` for mouse movement, clicks, and screenshots;
    ``keyboard`` for keyboard events and hotkeys; and ``mouse`` for
    drag operations.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize the Windows input provider.

        Args:
            config: Provider configuration dict (e.g. ``mouse_delay``).

        """
        self._config = config or {}
        self._connected = False
        self._pyautogui: Any = None
        self._keyboard: Any = None
        self._mouse: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to the Windows desktop input stack.

        Raises:
            ConnectionFailedError: If pyautogui/keyboard/mouse are not
                installed.

        """
        if not _check_libraries():
            raise ConnectionFailedError(
                "Windows input libraries (pyautogui, keyboard, mouse) are not installed"
            )
        import keyboard
        import mouse
        import pyautogui

        pyautogui.PAUSE = self._config.get("mouse_delay", 0.01)
        pyautogui.FAILSAFE = False
        self._pyautogui = pyautogui
        self._keyboard = keyboard
        self._mouse = mouse
        self._connected = True

    def disconnect(self) -> None:
        """Disconnect and release library references."""
        self._connected = False
        self._pyautogui = None
        self._keyboard = None
        self._mouse = None

    def is_connected(self) -> bool:
        """Return whether the provider is connected."""
        return self._connected

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return the screen resolution as ``(width, height)``."""
        self._ensure_connected()
        return self._pyautogui.size()  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Mouse / touch
    # ------------------------------------------------------------------

    def click(self, x: int, y: int, button: Button = "left") -> None:
        """Click at screen coordinates using pyautogui."""
        self._ensure_connected()
        self._pyautogui.click(x, y, button=button)

    def double_click(self, x: int, y: int) -> None:
        """Double-click at screen coordinates using pyautogui."""
        self._ensure_connected()
        self._pyautogui.doubleClick(x, y)

    def right_click(self, x: int, y: int) -> None:
        """Right-click at screen coordinates using pyautogui."""
        self._ensure_connected()
        self._pyautogui.rightClick(x, y)

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move the mouse pointer using pyautogui."""
        self._ensure_connected()
        self._pyautogui.moveTo(x, y, duration=duration)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        """Drag from one coordinate to another using pyautogui + mouse."""
        self._ensure_connected()
        self._pyautogui.moveTo(x1, y1)
        self._mouse.drag(x2, y2, duration=duration)

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Scroll using pyautogui."""
        self._ensure_connected()
        self._pyautogui.scroll(clicks, x=x, y=y)

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    def key_down(self, key: Key) -> None:
        """Press and hold a key using the keyboard library."""
        self._ensure_connected()
        self._keyboard.press(key)

    def key_up(self, key: Key) -> None:
        """Release a held key using the keyboard library."""
        self._ensure_connected()
        self._keyboard.release(key)

    def press_key(self, key: Key) -> None:
        """Press and release a key using the keyboard library."""
        self._ensure_connected()
        self._keyboard.send(key)

    def type_text(self, text: str) -> None:
        """Type text using the keyboard library."""
        self._ensure_connected()
        self._keyboard.write(text, delay=0.0)

    def hotkey(self, *keys: Key) -> None:
        """Press a combination of keys simultaneously."""
        self._ensure_connected()
        self._keyboard.send("+".join(keys))

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def wait(self, seconds: float) -> None:
        """Sleep for the specified duration."""
        time.sleep(seconds)

    def take_screenshot(self, path: str | None = None) -> bytes | None:
        """Capture a screenshot using pyautogui."""
        self._ensure_connected()
        img = self._pyautogui.screenshot()
        if path is not None:
            img.save(path)
            return None
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectionFailedError("WindowsInputProvider is not connected")
