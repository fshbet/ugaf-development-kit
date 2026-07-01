"""Mock and replay screenshot providers for testing and offline development."""

from __future__ import annotations

from pathlib import Path

import numpy

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

__all__ = [
    "ImageReplayProvider",
    "MockScreenshotProvider",
]

_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp")


class MockScreenshotProvider(ScreenshotProvider):
    """Screenshot provider that returns a synthetic or fixed static image.

    Useful for running plugins and vision-pipeline tests without a real
    device attached — either a solid-color placeholder of a configured
    size, or a single fixed image every capture returns.
    """

    def __init__(
        self,
        imaging: ImagingManager,
        width: int = 1080,
        height: int = 1920,
        color: tuple[int, int, int] = (0, 0, 0),
        static_image: Image | None = None,
    ) -> None:
        """Initialize the mock screenshot provider.

        Args:
            imaging: Used to access the backend that wraps generated
                image data.
            width: Synthetic image width in pixels (ignored if
                *static_image* is given).
            height: Synthetic image height in pixels (ignored if
                *static_image* is given).
            color: BGR fill color for the synthetic image.
            static_image: If provided, every capture returns this exact
                image instead of generating a new solid-color one.

        """
        self._imaging = imaging
        self._width = width
        self._height = height
        self._color = color
        self._static_image = static_image

    def capture_full(self) -> Image:
        """Return the configured static image, or a freshly generated solid-color one."""
        if self._static_image is not None:
            return self._static_image
        data = numpy.full((self._height, self._width, 3), self._color, dtype=numpy.uint8)
        return Image(data, self._imaging.backend)

    def capture_region(self, region: Region) -> Image:
        """Capture the full (synthetic) screen and crop to *region*."""
        return self.capture_full().crop(region.x, region.y, region.width, region.height)

    def capture_game_window(self, window_title: str) -> Image:
        """Return the same synthetic image regardless of *window_title*."""
        return self.capture_full()


class ImageReplayProvider(ScreenshotProvider):
    """Screenshot provider that replays a fixed sequence of pre-captured images.

    Useful for deterministic tests and offline plugin development
    against a recorded gameplay session instead of a live device.
    """

    def __init__(
        self,
        imaging: ImagingManager,
        paths: list[str | Path] | None = None,
        directory: str | Path | None = None,
        loop: bool = True,
    ) -> None:
        """Initialize the replay provider from an explicit list or a directory.

        Args:
            imaging: Used to load each image file.
            paths: Explicit ordered list of image file paths. Takes
                precedence over *directory* if both are given.
            directory: Directory to scan for image files
                (``.png``/``.jpg``/``.jpeg``/``.bmp``), sorted by name.
            loop: If ``True``, capture wraps back to the first image
                after the last; if ``False``, raises
                :class:`~ugaf.vision.exceptions.ScreenshotError` once
                exhausted.

        Raises:
            ValueError: If neither *paths* nor *directory* is given.
            ScreenshotError: If no image files are found.

        """
        if paths is not None:
            self._paths = [Path(p) for p in paths]
        elif directory is not None:
            self._paths = sorted(
                p for p in Path(directory).iterdir() if p.suffix.lower() in _IMAGE_EXTENSIONS
            )
        else:
            raise ValueError("Either paths or directory must be provided")

        if not self._paths:
            raise ScreenshotError("ImageReplayProvider found no images to replay")

        self._imaging = imaging
        self._loop = loop
        self._index = 0

    @property
    def remaining(self) -> int:
        """Return how many images have not yet been served (ignoring looping)."""
        return max(0, len(self._paths) - self._index)

    def capture_full(self) -> Image:
        """Return the next image in the sequence, loading it from disk.

        Raises:
            ScreenshotError: If the sequence is exhausted and
                ``loop=False``.

        """
        if self._index >= len(self._paths):
            if not self._loop:
                raise ScreenshotError("ImageReplayProvider exhausted (loop=False)")
            self._index = 0
        path = self._paths[self._index]
        self._index += 1
        return self._imaging.load(path)

    def capture_region(self, region: Region) -> Image:
        """Return the next image in the sequence, cropped to *region*."""
        return self.capture_full().crop(region.x, region.y, region.width, region.height)

    def capture_game_window(self, window_title: str) -> Image:
        """Return the next image in the sequence regardless of *window_title*."""
        return self.capture_full()
