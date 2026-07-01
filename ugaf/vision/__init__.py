"""Vision engine for UGAF game automation.

Provides screen capture, region/pixel/color analysis, template matching,
and feature detection.  Consumes the imaging engine internally; games
interact only with the :class:`~ugaf.vision.manager.VisionManager`.
"""

from ugaf.vision.adb_screenshot import AdbScreenshotProvider
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
from ugaf.vision.mock_screenshot import ImageReplayProvider, MockScreenshotProvider
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager
from ugaf.vision.screenshot_manager import registry as screenshot_registry

# Register built-in providers during application bootstrap.
screenshot_registry.register("adb", AdbScreenshotProvider)
screenshot_registry.register("mock", MockScreenshotProvider)
screenshot_registry.register("replay", ImageReplayProvider)

__all__ = [
    "AdbScreenshotProvider",
    "ColorMatchError",
    "DetectionError",
    "ImageReplayProvider",
    "MockScreenshotProvider",
    "OCRError",
    "PixelMatchError",
    "Region",
    "RegionNotFoundError",
    "ScreenshotError",
    "ScreenshotManager",
    "ScreenshotProvider",
    "TemplateMatchError",
    "VisionError",
    "VisionManager",
    "screenshot_registry",
]
