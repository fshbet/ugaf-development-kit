"""Tests for pixel-level operations."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.vision.color import Color
from ugaf.vision.exceptions import PixelMatchError
from ugaf.vision.pixel import Pixel, scan_pixels, wait_for_pixel
from ugaf.vision.region import Region


@pytest.fixture
def mock_backend() -> MagicMock:
    return MagicMock(spec=ImageBackend)


@pytest.fixture
def sample_image(mock_backend: MagicMock) -> Image:
    data = np.zeros((100, 200, 3), dtype=np.uint8)
    data[10, 20] = [0, 0, 255]  # BGR = (B=0, G=0, R=255) => Color(255, 0, 0)
    data[50, 60] = [0, 255, 0]  # BGR green at (60, 50)
    mock_backend.width.return_value = 200
    mock_backend.height.return_value = 100
    return Image(data, mock_backend)


class TestPixel:
    def test_attributes(self) -> None:
        p = Pixel(x=10, y=20, color=Color(255, 0, 0))
        assert p.x == 10
        assert p.y == 20
        assert p.color == Color(255, 0, 0)

    def test_immutable(self) -> None:
        p = Pixel(1, 2, Color(0, 0, 0))
        with pytest.raises(AttributeError):
            p.x = 99  # type: ignore[misc]


class TestScanPixels:
    def test_scan_full_image(self, sample_image: Image) -> None:
        pixels = scan_pixels(sample_image)
        assert len(pixels) == 200 * 100

    def test_scan_region(self, sample_image: Image) -> None:
        region = Region(0, 0, 10, 10)
        pixels = scan_pixels(sample_image, region=region)
        assert len(pixels) == 100

    def test_scan_region_bounds(self, sample_image: Image) -> None:
        region = Region(0, 0, 300, 10)
        with pytest.raises(PixelMatchError):
            scan_pixels(sample_image, region=region)

    def test_scan_negative_region(self, sample_image: Image) -> None:
        region = Region(-1, 0, 10, 10)
        with pytest.raises(PixelMatchError):
            scan_pixels(sample_image, region=region)

    def test_contains_expected_pixel(self, sample_image: Image) -> None:
        pixels = scan_pixels(sample_image, region=Region(15, 5, 10, 10))
        found = any(p.x == 20 and p.y == 10 and p.color == Color(255, 0, 0) for p in pixels)
        assert found


class TestWaitForPixel:
    def test_matches(self, sample_image: Image) -> None:
        assert wait_for_pixel(sample_image, Color(255, 0, 0), x=20, y=10) is True

    def test_no_match(self, sample_image: Image) -> None:
        assert wait_for_pixel(sample_image, Color(0, 0, 0), x=20, y=10, threshold=1.0) is False

    def test_out_of_bounds(self, sample_image: Image) -> None:
        with pytest.raises(PixelMatchError):
            wait_for_pixel(sample_image, Color(0, 0, 0), x=999, y=999)

    def test_negative_coords(self, sample_image: Image) -> None:
        with pytest.raises(PixelMatchError):
            wait_for_pixel(sample_image, Color(0, 0, 0), x=-1, y=0)

    def test_custom_threshold(self, sample_image: Image) -> None:
        data = sample_image.data
        data[30, 40] = [100, 100, 100]
        assert wait_for_pixel(sample_image, Color(105, 100, 95), x=40, y=30, threshold=10) is True
        assert wait_for_pixel(sample_image, Color(200, 100, 95), x=40, y=30, threshold=10) is False
