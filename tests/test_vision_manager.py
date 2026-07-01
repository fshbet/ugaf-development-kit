"""Tests for the VisionManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.color import Color
from ugaf.vision.exceptions import OCRError, ScreenshotError
from ugaf.vision.manager import VisionManager
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock(spec=ImageBackend)
    data = np.zeros((100, 200, 3), dtype=np.uint8)
    backend.load.return_value = data
    backend.width.return_value = 200
    backend.height.return_value = 100
    backend.match_template.return_value = np.zeros((51, 151), dtype=np.float32)
    return backend


@pytest.fixture
def mock_imaging(mock_backend: MagicMock) -> ImagingManager:
    mgr = MagicMock(spec=ImagingManager)
    img = Image(np.zeros((100, 200, 3), dtype=np.uint8), mock_backend)
    mgr.load.return_value = img
    mgr.backend = mock_backend
    return mgr


@pytest.fixture
def mock_screenshot_provider() -> MagicMock:
    provider = MagicMock(spec=ScreenshotProvider)
    backend = MagicMock(spec=ImageBackend)
    img = Image(np.zeros((100, 200, 3), dtype=np.uint8), backend)
    provider.capture_full.return_value = img
    provider.capture_region.return_value = img
    provider.capture_game_window.return_value = img
    return provider


class TestVisionManagerConstruction:
    def test_creates_with_default_imaging(self) -> None:
        with patch("ugaf.imaging.manager.ImagingManager") as mock_imaging_cls:
            mock_imaging_cls.return_value = MagicMock(spec=ImagingManager)
            vm = VisionManager()
            assert vm._imaging is not None

    def test_creates_with_explicit_imaging(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        assert vm._imaging is mock_imaging

    def test_creates_with_screenshot_provider(
        self, mock_imaging: ImagingManager, mock_screenshot_provider: MagicMock
    ) -> None:
        vm = VisionManager(imaging=mock_imaging, screenshot_provider=mock_screenshot_provider)
        assert vm._screenshot is mock_screenshot_provider


class TestVisionManagerScreenshot:
    def test_screenshot_raises_without_provider(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        with pytest.raises(ScreenshotError):
            vm.screenshot()

    def test_screenshot_with_provider(
        self, mock_imaging: ImagingManager, mock_screenshot_provider: MagicMock
    ) -> None:
        vm = VisionManager(imaging=mock_imaging, screenshot_provider=mock_screenshot_provider)
        img = vm.screenshot()
        assert isinstance(img, Image)
        mock_screenshot_provider.capture_full.assert_called_once()

    def test_screenshot_region(
        self, mock_imaging: ImagingManager, mock_screenshot_provider: MagicMock
    ) -> None:
        vm = VisionManager(imaging=mock_imaging, screenshot_provider=mock_screenshot_provider)
        region = Region(10, 10, 100, 100)
        img = vm.screenshot_region(region)
        assert isinstance(img, Image)
        mock_screenshot_provider.capture_region.assert_called_once_with(region)

    def test_screenshot_window(
        self, mock_imaging: ImagingManager, mock_screenshot_provider: MagicMock
    ) -> None:
        vm = VisionManager(imaging=mock_imaging, screenshot_provider=mock_screenshot_provider)
        img = vm.screenshot_window("My Game")
        assert isinstance(img, Image)
        mock_screenshot_provider.capture_game_window.assert_called_once_with("My Game")


class TestVisionManagerTemplate:
    def test_find_template_none(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        backend = MagicMock(spec=ImageBackend)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        backend.match_template.return_value = np.zeros((51, 151), dtype=np.float32)
        source = Image(data, backend)
        template = Image(data[:10, :10], backend)
        result = vm.find_template(source, template, confidence=0.99)
        assert result is None

    def test_load_image(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        img = vm.load_image(Path("test.png"))
        assert isinstance(img, Image)
        mock_imaging.load.assert_called_once_with(Path("test.png"))  # type: ignore[attr-defined]


class TestVisionManagerPixel:
    def test_pixel_matches(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        backend = MagicMock(spec=ImageBackend)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        data[10, 20] = [0, 0, 255]  # BGR = (B=0, G=0, R=255) => Color(255, 0, 0)
        img = Image(data, backend)
        assert vm.pixel_matches(img, 20, 10, Color(255, 0, 0)) is True
        assert vm.pixel_matches(img, 20, 10, Color(0, 0, 0), threshold=1.0) is False

    def test_scan_region(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        backend = MagicMock(spec=ImageBackend)
        data = np.zeros((10, 10, 3), dtype=np.uint8)
        img = Image(data, backend)
        pixels = vm.scan_region(img, Region(0, 0, 5, 5))
        assert len(pixels) == 25


class TestVisionManagerOCR:
    def test_ocr_raises(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        with pytest.raises(OCRError):
            vm.ocr_text(MagicMock(spec=Image))


class TestVisionManagerDetect:
    def test_detect_contours(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        backend = MagicMock(spec=ImageBackend)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        gray_data = np.zeros((100, 200), dtype=np.uint8)
        backend.grayscale.return_value = gray_data
        img = Image(data, backend)
        results = vm.detect_contours(img)
        assert isinstance(results, list)

    def test_detect_blobs(self, mock_imaging: ImagingManager) -> None:
        vm = VisionManager(imaging=mock_imaging)
        backend = MagicMock(spec=ImageBackend)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        gray_data = np.ones((100, 200), dtype=np.uint8) * 128
        backend.grayscale.return_value = gray_data
        img = Image(data, backend)
        results = vm.detect_blobs(img)
        assert isinstance(results, list)
