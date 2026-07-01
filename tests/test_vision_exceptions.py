"""Tests for vision exception hierarchy."""

from __future__ import annotations

import pytest

from ugaf.core.exceptions import UGAFError
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


class TestVisionExceptions:
    def test_vision_error_base(self) -> None:
        assert issubclass(VisionError, UGAFError)

    def test_region_not_found(self) -> None:
        assert issubclass(RegionNotFoundError, VisionError)

    def test_color_match_error(self) -> None:
        assert issubclass(ColorMatchError, VisionError)

    def test_pixel_match_error(self) -> None:
        assert issubclass(PixelMatchError, VisionError)

    def test_screenshot_error(self) -> None:
        assert issubclass(ScreenshotError, VisionError)

    def test_template_match_error(self) -> None:
        assert issubclass(TemplateMatchError, VisionError)

    def test_detection_error(self) -> None:
        assert issubclass(DetectionError, VisionError)

    def test_ocr_error(self) -> None:
        assert issubclass(OCRError, VisionError)

    def test_all_exceptions_raise(self) -> None:
        for exc_cls in (
            RegionNotFoundError,
            ColorMatchError,
            PixelMatchError,
            ScreenshotError,
            TemplateMatchError,
            DetectionError,
            OCRError,
        ):
            with pytest.raises(VisionError):
                raise exc_cls("test")
