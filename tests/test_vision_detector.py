"""Tests for the FeatureDetector."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.vision.detector import FeatureDetector


@pytest.fixture
def mock_image() -> Image:
    backend = MagicMock(spec=ImageBackend)
    data = np.zeros((100, 200, 3), dtype=np.uint8)
    backend.grayscale.return_value = data
    return Image(data, backend)


class TestFeatureDetector:
    def test_find_contours(self, mock_image: Image) -> None:
        detector = FeatureDetector()
        gray = mock_image.grayscale()
        gray_backend = gray._backend
        gray_backend.grayslice = None  # type: ignore[attr-defined]
        results = detector.find_contours(mock_image)
        assert isinstance(results, list)

    def test_find_contours_with_area_filters(self, mock_image: Image) -> None:
        detector = FeatureDetector()
        results = detector.find_contours(mock_image, min_area=50, max_area=5000)
        assert isinstance(results, list)

    def test_find_blobs(self, mock_image: Image) -> None:
        detector = FeatureDetector()
        results = detector.find_blobs(mock_image)
        assert isinstance(results, list)

    def test_find_lines(self, mock_image: Image) -> None:
        detector = FeatureDetector()
        results = detector.find_lines(mock_image)
        assert isinstance(results, list)

    def test_detected_feature_attributes(self) -> None:
        from ugaf.vision.detector import DetectedFeature
        from ugaf.vision.region import Region

        region = Region(10, 20, 100, 200)
        feat = DetectedFeature(region=region, confidence=0.95, label="button")
        assert feat.region == region
        assert feat.confidence == 0.95
        assert feat.label == "button"
