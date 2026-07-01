"""Exception hierarchy for the vision engine."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "ColorMatchError",
    "DetectionError",
    "OCRError",
    "PixelMatchError",
    "RegionNotFoundError",
    "ScreenshotError",
    "TemplateMatchError",
    "VisionError",
]


class VisionError(UGAFError):
    """Base exception for all vision engine errors."""


class RegionNotFoundError(VisionError):
    """Raised when a requested screen region cannot be located."""


class ColorMatchError(VisionError):
    """Raised when a colour comparison fails or colour is not found."""


class PixelMatchError(VisionError):
    """Raised when a pixel-level check fails."""


class ScreenshotError(VisionError):
    """Raised when a screenshot cannot be captured."""


class TemplateMatchError(VisionError):
    """Raised when template matching encounters an error."""


class DetectionError(VisionError):
    """Raised when feature detection fails."""


class OCRError(VisionError):
    """Raised when OCR processing fails."""
