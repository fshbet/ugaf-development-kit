"""OpenCV-based image processing backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.exceptions import ImageLoadError, ImageSaveError

__all__ = [
    "OpenCVBackend",
]

_INTERPOLATION_MAP: dict[str, int] = {
    "linear": 1,
    "cubic": 2,
    "nearest": 0,
    "lanczos": 4,
}

_METHOD_MAP: dict[str, int] = {
    "ccorr": 0,
    "ccorr_normed": 3,
    "ccoeff": 2,
    "ccoeff_normed": 4,
    "sqdiff": 1,
    "sqdiff_normed": 5,
}

_LIBRARIES_AVAILABLE: bool | None = None


def _check_opencv() -> bool:
    """Lazy-check whether OpenCV is installed."""
    global _LIBRARIES_AVAILABLE  # noqa: PLW0603
    if _LIBRARIES_AVAILABLE is not None:
        return _LIBRARIES_AVAILABLE
    try:
        import cv2  # noqa: F401
    except ImportError:
        _LIBRARIES_AVAILABLE = False
    else:
        _LIBRARIES_AVAILABLE = True
    return _LIBRARIES_AVAILABLE


class OpenCVBackend(ImageBackend):
    """Image processing backend using OpenCV (``cv2``).

    Every transformation returns new data, preserving the immutable
    contract.
    """

    def __init__(self) -> None:
        """Initialise the OpenCV backend.

        Raises:
            BackendNotAvailableError: If OpenCV is not installed.

        """
        if not _check_opencv():
            from ugaf.imaging.exceptions import BackendNotAvailableError

            raise BackendNotAvailableError(
                "OpenCV is not installed. Install with: pip install ugaf[vision]"
            )
        import cv2

        self._cv2 = cv2

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def load(self, path: str | Path) -> Any:
        """Load image from file."""
        import cv2

        data = cv2.imread(str(path))
        if data is None:
            raise ImageLoadError(f"Failed to load image: {path}")
        return data

    def save(self, data: Any, path: str | Path) -> None:
        """Save image to file."""
        import cv2

        success = cv2.imwrite(str(path), data)
        if not success:
            raise ImageSaveError(f"Failed to save image: {path}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    def width(self, data: Any) -> int:
        """Return image width in pixels."""
        return data.shape[1]  # type: ignore[no-any-return]

    def height(self, data: Any) -> int:
        """Return image height in pixels."""
        return data.shape[0]  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def crop(self, data: Any, x: int, y: int, width: int, height: int) -> Any:
        """Crop a rectangular region from the image."""
        return data[y : y + height, x : x + width].copy()

    def resize(self, data: Any, width: int, height: int, interpolation: str = "linear") -> Any:
        """Resize image to the given dimensions."""
        import cv2

        interp = _INTERPOLATION_MAP.get(interpolation, 1)
        return cv2.resize(data, (width, height), interpolation=interp)

    def rotate(self, data: Any, angle: float) -> Any:
        """Rotate image by the given angle (degrees)."""
        import cv2

        h, w = data.shape[:2]
        center = (w / 2, h / 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(data, matrix, (w, h))

    def scale(self, data: Any, factor: float) -> Any:
        """Scale image by the given factor."""
        import cv2

        h, w = data.shape[:2]
        new_w = max(1, int(w * factor))
        new_h = max(1, int(h * factor))
        return cv2.resize(data, (new_w, new_h), interpolation=1)

    def flip(self, data: Any, direction: str = "horizontal") -> Any:
        """Flip image horizontally or vertically."""
        import cv2

        flip_code = 1 if direction == "horizontal" else 0
        return cv2.flip(data, flip_code)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    def blur(self, data: Any, ksize: int = 5) -> Any:
        """Apply Gaussian blur to the image."""
        import cv2

        k = ksize if ksize % 2 == 1 else ksize + 1
        return cv2.GaussianBlur(data, (k, k), 0)

    def sharpen(self, data: Any) -> Any:
        """Sharpen the image using a kernel filter."""
        import cv2
        import numpy

        kernel = numpy.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=numpy.float32)
        return cv2.filter2D(data, -1, kernel)

    def normalize(self, data: Any) -> Any:
        """Normalize image pixel values to the 0–255 range."""
        import cv2

        return cv2.normalize(data, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)  # type: ignore[call-overload]

    # ------------------------------------------------------------------
    # Color / threshold
    # ------------------------------------------------------------------

    def threshold(self, data: Any, thresh: int = 128, maxval: int = 255) -> Any:
        """Apply binary threshold to the image."""
        import cv2

        if len(data.shape) == 3:
            gray = cv2.cvtColor(data, cv2.COLOR_BGR2GRAY)
        else:
            gray = data
        _, result = cv2.threshold(gray, thresh, maxval, cv2.THRESH_BINARY)
        return result

    def grayscale(self, data: Any) -> Any:
        """Convert image to grayscale."""
        import cv2

        if len(data.shape) == 2:
            return data
        return cv2.cvtColor(data, cv2.COLOR_BGR2GRAY)

    def invert(self, data: Any) -> Any:
        """Invert image colours."""
        import cv2

        return cv2.bitwise_not(data)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

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
        """Draw a rectangle on the image."""
        import cv2

        result = data.copy()
        cv2.rectangle(result, (x, y), (x + w, y + h), color, thickness)
        return result

    def draw_circle(
        self,
        data: Any,
        cx: int,
        cy: int,
        radius: int,
        color: tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> Any:
        """Draw a circle on the image."""
        import cv2

        result = data.copy()
        cv2.circle(result, (cx, cy), radius, color, thickness)
        return result

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
        """Draw text on the image."""
        import cv2

        result = data.copy()
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(result, text, (x, y), font, font_scale, color, thickness)
        return result

    # ------------------------------------------------------------------
    # Template matching
    # ------------------------------------------------------------------

    def match_template(self, data: Any, template: Any, method: str = "ccorr") -> Any:
        """Run template matching on the image."""
        import cv2

        method_code = _METHOD_MAP.get(method, 0)
        return cv2.matchTemplate(data, template, method_code)

    # ------------------------------------------------------------------
    # Encoding / decoding
    # ------------------------------------------------------------------

    def encode(self, data: Any, fmt: str = "png") -> bytes:
        """Encode image to bytes in the given format."""
        import cv2

        ext = f".{fmt}"
        _, encoded = cv2.imencode(ext, data)
        return bytes(encoded)

    def decode(self, data: bytes) -> Any:
        """Decode image from raw bytes."""
        import cv2
        import numpy

        buffer = numpy.frombuffer(data, dtype=numpy.uint8)
        img_data = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if img_data is None:
            raise ImageLoadError("Failed to decode image from bytes")
        return img_data
