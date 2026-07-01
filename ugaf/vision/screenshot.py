"""Screenshot provider abstraction for capturing screen content."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ugaf.imaging.image import Image
from ugaf.vision.region import Region

__all__ = [
    "ScreenshotProvider",
]


class ScreenshotProvider(ABC):
    """Abstract base class for screen capture backends.

    Implementations may use platform-specific APIs (Windows D3D,
    macOS CGDisplay, Linux X11/Wayland) or external tools (ADB).
    """

    @abstractmethod
    def capture_full(self) -> Image:
        """Capture the entire screen.

        Returns:
            An :class:`~ugaf.imaging.image.Image` containing the screen
            contents.

        """

    @abstractmethod
    def capture_region(self, region: Region) -> Image:
        """Capture a specific region of the screen.

        Args:
            region: The region to capture.

        Returns:
            An :class:`~ugaf.imaging.image.Image` containing only the
            requested region.

        """

    @abstractmethod
    def capture_game_window(self, window_title: str) -> Image:
        """Capture the content of a game window by its title.

        Args:
            window_title: Title of the target window.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the window's
            client area.

        """
