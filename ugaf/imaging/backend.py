"""Abstract image backend defining the image processing interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

__all__ = [
    "ImageBackend",
]


class ImageBackend(ABC):
    """Abstract base class for image processing backends.

    Every method that transforms image data returns new image data,
    leaving the original untouched (immutable contract).

    """

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    @abstractmethod
    def load(self, path: str | Path) -> Any:
        """Load image data from a file.

        Args:
            path: Path to the image file.

        Returns:
            Image data understood by this backend (typically a numpy
            array).

        Raises:
            ImageLoadError: If the file cannot be read.

        """

    @abstractmethod
    def save(self, data: Any, path: str | Path) -> None:
        """Save image data to a file.

        Args:
            data: Image data to save.
            path: Destination file path.

        Raises:
            ImageSaveError: If the file cannot be written.

        """

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @abstractmethod
    def width(self, data: Any) -> int:
        """Return the image width in pixels."""

    @abstractmethod
    def height(self, data: Any) -> int:
        """Return the image height in pixels."""

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    @abstractmethod
    def crop(self, data: Any, x: int, y: int, width: int, height: int) -> Any:
        """Crop a rectangular region from the image.

        Args:
            data: Source image data.
            x: Starting horizontal pixel.
            y: Starting vertical pixel.
            width: Region width.
            height: Region height.

        Returns:
            New image data containing the cropped region.

        """

    @abstractmethod
    def resize(self, data: Any, width: int, height: int, interpolation: str = "linear") -> Any:
        """Resize the image to the given dimensions.

        Args:
            data: Source image data.
            width: Target width.
            height: Target height.
            interpolation: Interpolation method
                (``"linear"``, ``"cubic"``, ``"nearest"``, ``"lanczos"``).

        Returns:
            New resized image data.

        """

    @abstractmethod
    def rotate(self, data: Any, angle: float) -> Any:
        """Rotate the image by the given angle (degrees, clockwise).

        Args:
            data: Source image data.
            angle: Rotation angle in degrees.

        Returns:
            New rotated image data.

        """

    @abstractmethod
    def scale(self, data: Any, factor: float) -> Any:
        """Scale the image by a multiplicative factor.

        Args:
            data: Source image data.
            factor: Scale factor (e.g. ``2.0`` doubles size).

        Returns:
            New scaled image data.

        """

    @abstractmethod
    def flip(self, data: Any, direction: str = "horizontal") -> Any:
        """Flip the image horizontally or vertically.

        Args:
            data: Source image data.
            direction: ``"horizontal"`` or ``"vertical"``.

        Returns:
            New flipped image data.

        """

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    @abstractmethod
    def blur(self, data: Any, ksize: int = 5) -> Any:
        """Apply Gaussian blur to the image.

        Args:
            data: Source image data.
            ksize: Kernel size (must be odd).

        Returns:
            New blurred image data.

        """

    @abstractmethod
    def sharpen(self, data: Any) -> Any:
        """Apply a sharpen filter to the image.

        Args:
            data: Source image data.

        Returns:
            New sharpened image data.

        """

    @abstractmethod
    def normalize(self, data: Any) -> Any:
        """Normalize pixel intensities to the full range.

        Args:
            data: Source image data.

        Returns:
            New normalized image data.

        """

    # ------------------------------------------------------------------
    # Color / threshold
    # ------------------------------------------------------------------

    @abstractmethod
    def threshold(self, data: Any, thresh: int = 128, maxval: int = 255) -> Any:
        """Apply a binary threshold to the image.

        Args:
            data: Source image data.
            thresh: Threshold value.
            maxval: Value assigned to pixels above the threshold.

        Returns:
            New thresholded image data.

        """

    @abstractmethod
    def grayscale(self, data: Any) -> Any:
        """Convert the image to grayscale.

        Args:
            data: Source image data.

        Returns:
            New grayscale image data.

        """

    @abstractmethod
    def invert(self, data: Any) -> Any:
        """Invert the image colours.

        Args:
            data: Source image data.

        Returns:
            New inverted image data.

        """

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    @abstractmethod
    def draw_rectangle(
        self,
        data: Any,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Any:
        """Draw a rectangle on the image.

        Args:
            data: Source image data.
            x: Top-left horizontal pixel.
            y: Top-left vertical pixel.
            w: Rectangle width.
            h: Rectangle height.
            color: BGR colour tuple.
            thickness: Line thickness (``-1`` for filled).

        Returns:
            New image data with the rectangle drawn.

        """

    @abstractmethod
    def draw_circle(
        self,
        data: Any,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Any:
        """Draw a circle on the image.

        Args:
            data: Source image data.
            cx: Center horizontal pixel.
            cy: Center vertical pixel.
            radius: Circle radius in pixels.
            color: BGR colour tuple.
            thickness: Line thickness (``-1`` for filled).

        Returns:
            New image data with the circle drawn.

        """

    @abstractmethod
    def draw_text(
        self,
        data: Any,
        text: str,
        x: int,
        y: int,
        font_scale: float = 1.0,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Any:
        """Draw text on the image.

        Args:
            data: Source image data.
            text: Text string to draw.
            x: Bottom-left horizontal pixel.
            y: Bottom-left vertical pixel.
            font_scale: Font scale factor.
            color: BGR colour tuple.
            thickness: Line thickness.

        Returns:
            New image data with the text drawn.

        """

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    @abstractmethod
    def match_template(self, data: Any, template: Any, method: str = "ccorr") -> Any:
        """Run template matching and return the result matrix.

        Args:
            data: Source image data.
            template: Template image data.
            method: Matching method (``"ccorr"``, ``"ccoeff"``,
                ``"sqdiff"``, or their normalized variants).

        Returns:
            Result matrix of matching scores.

        """

    # ------------------------------------------------------------------
    # Encoding / decoding
    # ------------------------------------------------------------------

    @abstractmethod
    def encode(self, data: Any, fmt: str = "png") -> bytes:
        """Encode image data to bytes.

        Args:
            data: Image data to encode.
            fmt: Output format (``"png"``, ``"jpeg"``, etc.).

        Returns:
            Encoded image bytes.

        Raises:
            ImageSaveError: If encoding fails.

        """

    @abstractmethod
    def decode(self, data: bytes) -> Any:
        """Decode image data from bytes.

        Args:
            data: Raw image bytes (PNG, JPEG, etc.).

        Returns:
            Decoded image data.

        Raises:
            ImageLoadError: If decoding fails.

        """
