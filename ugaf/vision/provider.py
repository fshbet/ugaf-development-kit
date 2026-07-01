"""Vision provider ABC — minimal interface for future swapping."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ugaf.imaging.image import Image
from ugaf.vision.color import Color
from ugaf.vision.detector import DetectedFeature
from ugaf.vision.matcher import MatchResult
from ugaf.vision.region import Region

__all__ = [
    "VisionProvider",
]


class VisionProvider(ABC):
    """Abstract vision provider that games can depend on.

    The default implementation is :class:`~ugaf.vision.manager.VisionManager`.
    Subclass this ABC to provide an alternative implementation for
    testing or platform-specific behaviour.
    """

    @abstractmethod
    def screenshot(self) -> Image:
        """Capture a full-screen screenshot.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the current screen.

        """

    @abstractmethod
    def screenshot_region(self, region: Region) -> Image:
        """Capture a specific screen region.

        Args:
            region: The region to capture.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the region.

        """

    @abstractmethod
    def find_template(
        self,
        source: Image,
        template: Image | str,
        confidence: float = 0.9,
    ) -> MatchResult | None:
        """Find the best template match in an image.

        Args:
            source: Image to search within.
            template: Template image (or path).
            confidence: Minimum confidence threshold.

        Returns:
            The best :class:`MatchResult`, or ``None``.

        """

    @abstractmethod
    def find_all_templates(
        self,
        source: Image,
        template: Image | str,
        confidence: float = 0.9,
    ) -> list[MatchResult]:
        """Find all template matches in an image.

        Args:
            source: Image to search within.
            template: Template image (or path).
            confidence: Minimum confidence threshold.

        Returns:
            A list of :class:`MatchResult` instances.

        """

    @abstractmethod
    def detect_contours(
        self,
        image: Image,
        min_area: int = 0,
        max_area: int = 0,
    ) -> list[DetectedFeature]:
        """Find contours in the image.

        Args:
            image: The source image.
            min_area: Minimum contour area filter.
            max_area: Maximum contour area filter.

        Returns:
            A list of detected features.

        """

    @abstractmethod
    @abstractmethod
    def pixel_matches(
        self,
        image: Image,
        x: int,
        y: int,
        color: Color,
        threshold: float = 30.0,
    ) -> bool:
        """Check whether a pixel matches the expected colour.

        Args:
            image: The source image.
            x: X coordinate.
            y: Y coordinate.
            color: Expected colour.
            threshold: Colour distance threshold.

        Returns:
            ``True`` if the pixel matches.

        """

    def scan_region(self, image: Image, region: Region | None = None) -> list:  # type: ignore[type-arg]
        """Scan all pixels in the given image (or region).

        Args:
            image: The source image.
            region: Optional sub-region.

        Returns:
            A list of Pixel instances.

        """
        raise NotImplementedError

    def detect_blobs(
        self,
        image: Image,
        min_area: int = 100,
        max_area: int = 5000,
    ) -> list[DetectedFeature]:
        """Find blobs in the image.

        Args:
            image: The source image.
            min_area: Minimum blob area.
            max_area: Maximum blob area.

        Returns:
            A list of DetectedFeature instances.

        """
        raise NotImplementedError

    def detect_lines(
        self,
        image: Image,
        threshold: int = 100,
    ) -> list[DetectedFeature]:
        """Find straight lines in the image.

        Args:
            image: The source image.
            threshold: Accumulator threshold.

        Returns:
            A list of DetectedFeature instances.

        """
        raise NotImplementedError

    def screenshot_window(self, window_title: str) -> Image:
        """Capture a game window by its title.

        Args:
            window_title: Title of the target window.

        Returns:
            An Image of the window.

        """
        raise NotImplementedError

    def ocr_text(self, image: Image) -> str:
        """Extract text from an image using OCR.

        Args:
            image: The image to perform OCR on.

        Returns:
            The extracted text string.

        """
        raise NotImplementedError

    def load_image(self, path: str) -> Image:
        """Load an image from a file.

        Args:
            path: Path to the image file.

        Returns:
            An Image.

        """
        raise NotImplementedError
