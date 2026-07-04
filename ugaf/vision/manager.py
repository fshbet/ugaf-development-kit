"""Vision manager — the primary vision entry point for game plugins."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from ugaf.core.metrics import MetricsSnapshot, MetricsTracker
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.color import Color
from ugaf.vision.detector import DetectedFeature, FeatureDetector
from ugaf.vision.exceptions import (
    ScreenshotError,
    VisionError,
)
from ugaf.vision.matcher import MatchResult, TemplateMatcher
from ugaf.vision.ocr import OCRProvider
from ugaf.vision.pixel import Pixel, scan_pixels, wait_for_pixel
from ugaf.vision.provider import VisionProvider
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

if TYPE_CHECKING:
    from ugaf.core.config import Config

__all__ = [
    "VisionManager",
]


class VisionManager(VisionProvider):
    """Vision manager — the primary vision entry point for game plugins.

    Composes :class:`~ugaf.imaging.manager.ImagingManager` with
    screen capture, template matching, feature detection, and colour
    analysis.

    Games resolve this class from the dependency injection container
    and never interact with the imaging engine directly.

    Usage::

        vision = context.service_container.resolve(VisionManager)

        # Screenshot
        screen = vision.screenshot()
        hp_bar = vision.screenshot_region(Region(10, 10, 200, 30))

        # Template matching
        result = vision.find_template(screen, "quest_icon.png", confidence=0.85)
        if result:
            click(result.center)

        # Colour checking
        matches = vision.pixel_matches(screen, 100, 50, Color(255, 0, 0))

    """

    def __init__(
        self,
        imaging: ImagingManager | None = None,
        screenshot_provider: ScreenshotProvider | None = None,
        config: Config | None = None,
    ) -> None:
        """Initialise the vision manager.

        Args:
            imaging: An :class:`~ugaf.imaging.manager.ImagingManager`
                instance.  Creates a default one if not provided.
            screenshot_provider: A :class:`ScreenshotProvider` instance.
                If not provided, screenshot methods raise
                :class:`ScreenshotError`.
            config: Optional configuration.  When provided the
                ``vision.*`` keys set defaults for template matching
                and pixel threshold.

        Raises:
            VisionError: If the imaging manager cannot be created.

        """
        try:
            self._imaging = imaging or ImagingManager(config=config)
        except Exception as exc:
            raise VisionError(f"Failed to create ImagingManager: {exc}") from exc

        self._screenshot = screenshot_provider
        self._config = config

        method = (
            config.get("vision.template_match_method", "ccorr_normed") if config else "ccorr_normed"
        )
        confidence = config.get("vision.template_confidence", 0.9) if config else 0.9
        self._pixel_threshold = config.get("vision.pixel_threshold", 30.0) if config else 30.0

        self._matcher = TemplateMatcher(
            self._imaging, default_method=method, default_confidence=confidence
        )
        self._detector = FeatureDetector()
        self._ocr = OCRProvider()
        self._processing_metrics = MetricsTracker()

    @property
    def processing_metrics(self) -> MetricsSnapshot:
        """Return frame-processing time metrics (rolling window).

        Measures wall-clock time spent in template matching — the
        "how long does it take to make sense of a frame" counterpart
        to :attr:`~ugaf.vision.screenshot_manager.ScreenshotManager.metrics`
        capture latency.
        """
        return self._processing_metrics.snapshot()

    # ------------------------------------------------------------------
    # Screenshot
    # ------------------------------------------------------------------

    def screenshot(self) -> Image:
        """Capture a full-screen screenshot.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the current screen.

        Raises:
            ScreenshotError: If no screenshot provider is configured.

        """
        if self._screenshot is None:
            raise ScreenshotError("No ScreenshotProvider configured")
        return self._screenshot.capture_full()

    def screenshot_region(self, region: Region) -> Image:
        """Capture a specific screen region.

        Args:
            region: The region to capture.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the region.

        Raises:
            ScreenshotError: If no screenshot provider is configured.

        """
        if self._screenshot is None:
            raise ScreenshotError("No ScreenshotProvider configured")
        return self._screenshot.capture_region(region)

    def screenshot_window(self, window_title: str) -> Image:
        """Capture a game window by its title.

        Args:
            window_title: Title of the target window.

        Returns:
            An :class:`~ugaf.imaging.image.Image` of the window.

        Raises:
            ScreenshotError: If no screenshot provider is configured.

        """
        if self._screenshot is None:
            raise ScreenshotError("No ScreenshotProvider configured")
        return self._screenshot.capture_game_window(window_title)

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    def find_template(
        self,
        source: Image,
        template: Image | str | Path,
        confidence: float = 0.9,
    ) -> MatchResult | None:
        """Find the best template match in an image.

        Args:
            source: Image to search within.
            template: Template image (or path).
            confidence: Minimum confidence threshold (0.0 – 1.0).

        Returns:
            The best :class:`MatchResult`, or ``None``.

        """
        with self._processing_metrics.measure():
            return self._matcher.find_best(source, template, confidence=confidence)

    def find_all_templates(
        self,
        source: Image,
        template: Image | str | Path,
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
        with self._processing_metrics.measure():
            return self._matcher.find_all(source, template, confidence=confidence)

    # ------------------------------------------------------------------
    # Feature detection
    # ------------------------------------------------------------------

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
            A list of :class:`DetectedFeature` instances.

        """
        return self._detector.find_contours(image, min_area=min_area, max_area=max_area)

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
            A list of :class:`DetectedFeature` instances.

        """
        return self._detector.find_blobs(image, min_area=min_area, max_area=max_area)

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
            A list of :class:`DetectedFeature` instances.

        """
        return self._detector.find_lines(image, threshold=threshold)

    # ------------------------------------------------------------------
    # Colour / pixel analysis
    # ------------------------------------------------------------------

    def pixel_matches(
        self,
        image: Image,
        x: int,
        y: int,
        color: Color,
        threshold: float | None = None,
    ) -> bool:
        """Check whether a pixel matches the expected colour.

        Args:
            image: The source image.
            x: X coordinate.
            y: Y coordinate.
            color: Expected colour.
            threshold: Colour distance threshold (uses config default
                when ``None``).

        Returns:
            ``True`` if the pixel colour matches.

        """
        return wait_for_pixel(
            image,
            color,
            x,
            y,
            threshold=threshold if threshold is not None else self._pixel_threshold,
        )

    def scan_region(self, image: Image, region: Region | None = None) -> list[Pixel]:
        """Scan all pixels in the given image (or region).

        Args:
            image: The source image.
            region: Optional sub-region.

        Returns:
            A list of :class:`Pixel` instances.

        """
        return scan_pixels(image, region=region)

    # ------------------------------------------------------------------
    # Waiting on templates
    # ------------------------------------------------------------------

    def wait_until_visible(
        self,
        template: Image | str | Path,
        timeout: float = 5.0,
        confidence: float = 0.9,
        poll_interval: float = 0.3,
    ) -> MatchResult | None:
        """Poll the screen until *template* appears, or *timeout* elapses.

        Reusable across any game/workflow that needs to wait for a UI
        element (a button, a dialog, a loading screen finishing) — the
        alternative to a caller hand-rolling its own capture/match/
        sleep loop.

        Args:
            template: Template image (or path) to look for.
            timeout: Maximum seconds to wait.
            confidence: Minimum match confidence threshold.
            poll_interval: Seconds between screenshot/match attempts.

        Returns:
            The first successful :class:`MatchResult`, or ``None`` if
            *timeout* elapses without a match.

        """
        deadline = time.monotonic() + timeout
        while True:
            match = self.find_template(self.screenshot(), template, confidence=confidence)
            if match is not None:
                return match
            if time.monotonic() >= deadline:
                return None
            time.sleep(poll_interval)

    def wait_until_hidden(
        self,
        template: Image | str | Path,
        timeout: float = 5.0,
        confidence: float = 0.9,
        poll_interval: float = 0.3,
    ) -> bool:
        """Poll the screen until *template* disappears, or *timeout* elapses.

        Args:
            template: Template image (or path) to look for.
            timeout: Maximum seconds to wait.
            confidence: Minimum match confidence threshold.
            poll_interval: Seconds between screenshot/match attempts.

        Returns:
            ``True`` once *template* is no longer found, ``False`` if
            it is still visible when *timeout* elapses.

        """
        deadline = time.monotonic() + timeout
        while True:
            match = self.find_template(self.screenshot(), template, confidence=confidence)
            if match is None:
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)

    # ------------------------------------------------------------------
    # Bar gauges (health, shadow meter, stamina, ...)
    # ------------------------------------------------------------------

    def measure_bar_fill(
        self,
        image: Image,
        region: Region,
        filled_color: Color,
        threshold: float | None = None,
    ) -> float:
        """Measure how much of a horizontal bar gauge is filled.

        Generic reusable primitive for any left-to-right depleting/
        filling bar (health, shadow/energy meter, stamina, a loading
        bar) — a game supplies the bar's screen *region* and the
        colour of its "filled" segment via its knowledge base; this
        function has no game-specific knowledge.

        Scans a single horizontal line through the middle of *region*
        from left to right and returns the fraction of pixels, up to
        the first non-matching pixel, that match *filled_color*.

        Args:
            image: The captured frame to measure.
            region: The bar's screen region.
            filled_color: The colour of the bar's filled segment.
            threshold: Colour distance threshold (uses config default
                when ``None``).

        Returns:
            Fraction filled, from ``0.0`` (empty) to ``1.0`` (full).

        """
        if region.width <= 0:
            return 0.0
        match_threshold = threshold if threshold is not None else self._pixel_threshold
        row_y = region.y + region.height // 2
        filled = 0
        for dx in range(region.width):
            if self.pixel_matches(image, region.x + dx, row_y, filled_color, match_threshold):
                filled = dx + 1
            else:
                break
        return filled / region.width

    # ------------------------------------------------------------------
    # OCR (stub)
    # ------------------------------------------------------------------

    def ocr_text(self, image: Image) -> str:
        """Extract text from an image using OCR.

        Args:
            image: The image to perform OCR on.

        Returns:
            The extracted text string.

        Raises:
            OCRError: Always — OCR is not yet implemented.

        """
        return self._ocr.extract_text(image)

    # ------------------------------------------------------------------
    # Image loading (delegated to imaging manager)
    # ------------------------------------------------------------------

    def load_image(self, path: str | Path) -> Image:
        """Load an image from a file.

        Args:
            path: Path to the image file.

        Returns:
            An :class:`~ugaf.imaging.image.Image`.

        """
        return self._imaging.load(path)
