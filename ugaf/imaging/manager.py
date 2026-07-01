"""Imaging manager — entry point for image loading and creation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.exceptions import BackendNotAvailableError, ImageLoadError
from ugaf.imaging.image import Image

if TYPE_CHECKING:
    from ugaf.core.config import Config

__all__ = [
    "ImagingManager",
]


class ImagingManager:
    """Central image-loading service.

    Games should never use this class directly.  It is consumed by
    :class:`~ugaf.vision.manager.VisionManager`.

    Usage::

        manager = ImagingManager()
        img = manager.load("screenshot.png")
    """

    def __init__(
        self,
        backend: ImageBackend | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialise the imaging manager.

        Args:
            backend: An :class:`ImageBackend` instance.  Defaults to
                :class:`~ugaf.imaging.opencv_backend.OpenCVBackend` if
                OpenCV is installed.
            config: Optional configuration.  When provided the
                ``imaging.backend`` key selects the backend type.

        Raises:
            BackendNotAvailableError: If no backend is provided and
                OpenCV is not available.

        """
        if backend is not None:
            self._backend = backend
        else:
            self._backend = self._create_backend(config)

    @staticmethod
    def _create_backend(config: Config | None) -> ImageBackend:
        backend_name = config.get("imaging.backend", "opencv") if config else "opencv"
        if backend_name == "opencv":
            from ugaf.imaging.opencv_backend import OpenCVBackend

            return OpenCVBackend()
        raise BackendNotAvailableError(f"Unknown imaging backend: {backend_name}")

    def load(self, path: str | Path) -> Image:
        """Load an image from a file.

        Args:
            path: Path to the image file.

        Returns:
            An :class:`Image` wrapping the loaded data.

        Raises:
            ImageLoadError: If the file cannot be read.

        """
        data = self._backend.load(path)
        return Image(data, self._backend)

    def from_bytes(self, data: bytes) -> Image:
        """Create an image from raw bytes (e.g. screenshot PNG).

        Args:
            data: Raw image bytes (PNG, JPEG, etc.).

        Returns:
            An :class:`Image` wrapping the decoded data.

        Raises:
            ImageLoadError: If the bytes cannot be decoded.

        """
        import numpy

        buffer = numpy.frombuffer(data, dtype=numpy.uint8)
        import cv2

        img_data = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if img_data is None:
            raise ImageLoadError("Failed to decode image from bytes")
        return Image(img_data, self._backend)

    @property
    def backend(self) -> ImageBackend:
        """Return the underlying image backend."""
        return self._backend
