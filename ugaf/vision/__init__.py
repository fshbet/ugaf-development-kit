"""Vision engine for UGAF game automation.

Provides screen capture, region/pixel/color analysis, template matching,
and feature detection.  Consumes the imaging engine internally; games
interact only with the :class:`~ugaf.vision.manager.VisionManager`.
"""

from ugaf.vision.exceptions import (
    ColorMatchError,
    DetectionError,
    OCRError,
    PixelMatchError,
    RegionNotFoundError,
    ScreenshotError,
    TemplateMatchError,
    VisionError,
)
from ugaf.vision.manager import VisionManager
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

__all__ = [
    "ColorMatchError",
    "DetectionError",
    "OCRError",
    "PixelMatchError",
    "Region",
    "RegionNotFoundError",
    "ScreenshotError",
    "ScreenshotProvider",
    "TemplateMatchError",
    "VisionError",
    "VisionManager",
]
