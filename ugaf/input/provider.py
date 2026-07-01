"""Abstract input provider defining the platform-agnostic automation interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ugaf.input.types import Button, Key

__all__ = [
    "InputProvider",
]


class InputProvider(ABC):
    """Abstract base class for platform-specific input providers.

    Each subclass implements the full input automation interface for a
    specific platform (Windows, Android, etc.).
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialise the provider.

        Args:
            config: Optional configuration dict.

        """
        self._config = config or {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the target platform.

        Raises:
            ConnectionFailedError: If the connection cannot be established.
            DeviceNotFoundError: If the target device is not found.

        """

    @abstractmethod
    def disconnect(self) -> None:
        """Tear down the connection to the target platform."""

    @abstractmethod
    def is_connected(self) -> bool:
        """Return whether the provider is currently connected."""

    # ------------------------------------------------------------------
    # Mouse / touch
    # ------------------------------------------------------------------

    @abstractmethod
    def click(self, x: int, y: int, button: Button = "left") -> None:
        """Click at the given screen coordinates.

        Args:
            x: Horizontal pixel position.
            y: Vertical pixel position.
            button: Mouse button (``"left"``, ``"right"``,
                ``"middle"``).

        """

    @abstractmethod
    def double_click(self, x: int, y: int) -> None:
        """Double-click at the given screen coordinates.

        Args:
            x: Horizontal pixel position.
            y: Vertical pixel position.

        """

    @abstractmethod
    def right_click(self, x: int, y: int) -> None:
        """Right-click at the given screen coordinates.

        Args:
            x: Horizontal pixel position.
            y: Vertical pixel position.

        """

    @abstractmethod
    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        """Move the mouse pointer to the given screen coordinates.

        Args:
            x: Horizontal pixel position.
            y: Vertical pixel position.
            duration: Time in seconds the movement should take.

        """

    @abstractmethod
    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        """Drag from one coordinate to another.

        Args:
            x1: Starting horizontal pixel position.
            y1: Starting vertical pixel position.
            x2: Ending horizontal pixel position.
            y2: Ending vertical pixel position.
            duration: Time in seconds the drag should take.

        """

    @abstractmethod
    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        """Scroll at the current or given position.

        Args:
            clicks: Number of scroll "clicks" (positive = up,
                negative = down).
            x: Horizontal pixel position for the scroll.
            y: Vertical pixel position for the scroll.

        """

    # ------------------------------------------------------------------
    # Keyboard
    # ------------------------------------------------------------------

    @abstractmethod
    def key_down(self, key: Key) -> None:
        """Press and hold a key.

        Args:
            key: Key name (e.g. ``"shift"``, ``"ctrl"``, ``"a"``).

        """

    @abstractmethod
    def key_up(self, key: Key) -> None:
        """Release a held key.

        Args:
            key: Key name (e.g. ``"shift"``, ``"ctrl"``, ``"a"``).

        """

    @abstractmethod
    def press_key(self, key: Key) -> None:
        """Press and release a key.

        Args:
            key: Key name (e.g. ``"enter"``, ``"space"``).

        """

    @abstractmethod
    def type_text(self, text: str) -> None:
        """Type a string of text.

        Args:
            text: The text to type.

        """

    @abstractmethod
    def hotkey(self, *keys: Key) -> None:
        """Press a combination of keys simultaneously.

        Args:
            *keys: Key names (e.g. ``"ctrl"``, ``"c"``).

        """

    @property
    def screen_size(self) -> tuple[int, int]:
        """Return the screen resolution as ``(width, height)``."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @abstractmethod
    def wait(self, seconds: float) -> None:
        """Wait for the specified duration.

        Args:
            seconds: Number of seconds to wait.

        """

    @abstractmethod
    def take_screenshot(self, path: str | None = None) -> bytes | None:
        """Capture a screenshot.

        Args:
            path: Optional file path to save the screenshot. If not
                provided, the screenshot is returned as raw bytes.

        Returns:
            PNG image bytes if *path* is ``None``, else ``None``.

        """
