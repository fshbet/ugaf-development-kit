"""Immutable Image class with fluent operations."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy

from ugaf.imaging.types import ImageSize

if TYPE_CHECKING:
    from ugaf.imaging.backend import ImageBackend

__all__ = [
    "Image",
]


class Image:
    """Immutable image wrapper around backend image data.

    All transformation methods return a new :class:`Image`, leaving the
    original untouched.

    Usage::

        img = manager.load("screenshot.png")
        result = (
            img
            .crop(10, 10, 100, 100)
            .grayscale()
            .threshold()
            .save("output.png")
        )
    """

    def __init__(self, data: Any, backend: ImageBackend) -> None:
        """Wrap existing image data with a backend.

        Args:
            data: Backend-specific image data (typically a numpy array).
            backend: The backing :class:`ImageBackend` instance.

        """
        self._data = data
        self._backend = backend

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def width(self) -> int:
        """Return the image width in pixels."""
        return self._backend.width(self._data)

    @property
    def height(self) -> int:
        """Return the image height in pixels."""
        return self._backend.height(self._data)

    @property
    def size(self) -> ImageSize:
        """Return the image dimensions."""
        return ImageSize(width=self.width, height=self.height)

    @property
    def data(self) -> Any:
        """Return the underlying image data."""
        return self._data

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def crop(self, x: int, y: int, width: int, height: int) -> Image:
        """Crop a rectangular region from the image.

        Args:
            x: Starting horizontal pixel.
            y: Starting vertical pixel.
            width: Region width.
            height: Region height.

        Returns:
            A new :class:`Image` with the cropped region.

        """
        new_data = self._backend.crop(self._data, x, y, width, height)
        return Image(new_data, self._backend)

    def resize(self, width: int, height: int, interpolation: str = "linear") -> Image:
        """Resize the image to the given dimensions.

        Args:
            width: Target width.
            height: Target height.
            interpolation: Interpolation method.

        Returns:
            A new resized :class:`Image`.

        """
        new_data = self._backend.resize(self._data, width, height, interpolation=interpolation)
        return Image(new_data, self._backend)

    def rotate(self, angle: float) -> Image:
        """Rotate the image clockwise by the given angle.

        Args:
            angle: Rotation angle in degrees.

        Returns:
            A new rotated :class:`Image`.

        """
        new_data = self._backend.rotate(self._data, angle)
        return Image(new_data, self._backend)

    def scale(self, factor: float) -> Image:
        """Scale the image by a multiplicative factor.

        Args:
            factor: Scale factor.

        Returns:
            A new scaled :class:`Image`.

        """
        new_data = self._backend.scale(self._data, factor)
        return Image(new_data, self._backend)

    def flip(self, direction: str = "horizontal") -> Image:
        """Flip the image horizontally or vertically.

        Args:
            direction: ``"horizontal"`` or ``"vertical"``.

        Returns:
            A new flipped :class:`Image`.

        """
        new_data = self._backend.flip(self._data, direction=direction)
        return Image(new_data, self._backend)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def blur(self, ksize: int = 5) -> Image:
        """Apply Gaussian blur.

        Args:
            ksize: Kernel size (must be odd).

        Returns:
            A new blurred :class:`Image`.

        """
        new_data = self._backend.blur(self._data, ksize=ksize)
        return Image(new_data, self._backend)

    def sharpen(self) -> Image:
        """Apply a sharpen filter.

        Returns:
            A new sharpened :class:`Image`.

        """
        new_data = self._backend.sharpen(self._data)
        return Image(new_data, self._backend)

    def normalize(self) -> Image:
        """Normalise pixel intensities to the full range.

        Returns:
            A new normalized :class:`Image`.

        """
        new_data = self._backend.normalize(self._data)
        return Image(new_data, self._backend)

    # ------------------------------------------------------------------
    # Color / threshold
    # ------------------------------------------------------------------

    def threshold(self, thresh: int = 128, maxval: int = 255) -> Image:
        """Apply a binary threshold.

        Args:
            thresh: Threshold value.
            maxval: Value for pixels above the threshold.

        Returns:
            A new thresholded :class:`Image`.

        """
        new_data = self._backend.threshold(self._data, thresh=thresh, maxval=maxval)
        return Image(new_data, self._backend)

    def grayscale(self) -> Image:
        """Convert to grayscale.

        Returns:
            A new grayscale :class:`Image`.

        """
        new_data = self._backend.grayscale(self._data)
        return Image(new_data, self._backend)

    def invert(self) -> Image:
        """Invert the image colours.

        Returns:
            A new inverted :class:`Image`.

        """
        new_data = self._backend.invert(self._data)
        return Image(new_data, self._backend)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw_rectangle(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Image:
        """Draw a rectangle on the image.

        Args:
            x: Top-left horizontal pixel.
            y: Top-left vertical pixel.
            w: Rectangle width.
            h: Rectangle height.
            color: BGR colour tuple.
            thickness: Line thickness (``-1`` for filled).

        Returns:
            A new :class:`Image` with the rectangle drawn.

        """
        new_data = self._backend.draw_rectangle(
            self._data, x, y, w, h, color=color, thickness=thickness
        )
        return Image(new_data, self._backend)

    def draw_circle(
        self,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Image:
        """Draw a circle on the image.

        Args:
            cx: Center horizontal pixel.
            cy: Center vertical pixel.
            radius: Circle radius in pixels.
            color: BGR colour tuple.
            thickness: Line thickness (``-1`` for filled).

        Returns:
            A new :class:`Image` with the circle drawn.

        """
        new_data = self._backend.draw_circle(
            self._data, cx, cy, radius, color=color, thickness=thickness
        )
        return Image(new_data, self._backend)

    def draw_text(
        self,
        text: str,
        x: int,
        y: int,
        font_scale: float = 1.0,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Image:
        """Draw text on the image.

        Args:
            text: Text string to draw.
            x: Bottom-left horizontal pixel.
            y: Bottom-left vertical pixel.
            font_scale: Font scale factor.
            color: BGR colour tuple.
            thickness: Line thickness.

        Returns:
            A new :class:`Image` with the text drawn.

        """
        new_data = self._backend.draw_text(
            self._data, text, x, y, font_scale=font_scale, color=color, thickness=thickness
        )
        return Image(new_data, self._backend)

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    def match_template(self, template: Image, method: str = "ccorr") -> Any:
        """Run template matching and return the raw result matrix.

        Args:
            template: The template image to search for.
            method: Matching method (``"ccorr"``, ``"ccoeff"``,
                ``"sqdiff"``, or normalized variants).

        Returns:
            The result matrix of matching scores.

        """
        return self._backend.match_template(self._data, template._data, method=method)

    def match(
        self,
        template: Image,
        method: str = "ccorr",
        confidence: float = 0.9,
    ) -> list[Image]:
        """Find all matches of *template* in this image.

        Args:
            template: The template image to search for.
            method: Matching method.
            confidence: Minimum confidence threshold.

        Returns:
            List of matched :class:`Image` regions.

        """
        result_data = self.match_template(template, method=method)
        max_loc = numpy.unravel_index(numpy.argmax(result_data), result_data.shape)
        max_val = float(result_data[max_loc])
        matches: list[Image] = []
        if max_val >= confidence:
            h, w = template._data.shape[:2]
            x, y = max_loc[1], max_loc[0]
            matches.append(self.crop(int(x), int(y), w, h))
        return matches

    def as_contiguous_array(self) -> Any:
        """Return a contiguous C-order copy of the image data.

        Required by OpenCV functions that operate on non-contiguous
        array slices.

        Returns:
            A contiguous numpy array.

        """
        return numpy.ascontiguousarray(self._data)

    def save(self, path: str | Path) -> None:
        """Save the image to a file.

        Args:
            path: Destination file path.

        """
        self._backend.save(self._data, path)
