"""Tests for the TemplateMatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.matcher import MatchResult, TemplateMatcher
from ugaf.vision.region import Region


@pytest.fixture
def source_backend() -> MagicMock:
    backend = MagicMock(spec=ImageBackend)
    source_data = np.zeros((200, 300, 3), dtype=np.uint8)
    backend.load.return_value = source_data
    backend.width.return_value = 300
    backend.height.return_value = 200
    return backend


@pytest.fixture
def template_backend() -> MagicMock:
    backend = MagicMock(spec=ImageBackend)
    tmpl_data = np.zeros((50, 50, 3), dtype=np.uint8)
    backend.load.return_value = tmpl_data
    backend.match_template.return_value = np.zeros((151, 251), dtype=np.float32)
    return backend


@pytest.fixture
def source_image(source_backend: MagicMock) -> Image:
    return Image(np.zeros((200, 300, 3), dtype=np.uint8), source_backend)


@pytest.fixture
def template_image(template_backend: MagicMock) -> Image:
    return Image(np.zeros((50, 50, 3), dtype=np.uint8), template_backend)


class TestMatchResult:
    def test_attributes(self) -> None:
        region = Region(10, 20, 100, 200)
        result = MatchResult(region=region, confidence=0.95)
        assert result.region == region
        assert result.confidence == 0.95

    def test_center(self) -> None:
        result = MatchResult(Region(10, 20, 100, 200), 0.9)
        assert result.center == (60, 120)

    def test_repr(self) -> None:
        result = MatchResult(Region(0, 0, 10, 10), 0.95)
        assert "MatchResult" in repr(result)
        assert "0.950" in repr(result)


class TestTemplateMatcher:
    def test_find_best_no_match(self, source_image: Image, template_image: Image) -> None:
        imaging = MagicMock(spec=ImagingManager)
        matcher = TemplateMatcher(imaging)
        bt = source_image._backend.match_template
        bt.return_value = np.zeros((151, 251), dtype=np.float32)  # type: ignore[attr-defined]
        result = matcher.find_best(source_image, template_image, confidence=0.9)
        assert result is None

    def test_find_best_with_match(self, source_image: Image, template_image: Image) -> None:
        result_data = np.zeros((151, 251), dtype=np.float32)
        result_data[50, 100] = 0.95
        bt = source_image._backend.match_template
        bt.return_value = result_data  # type: ignore[attr-defined]
        template_image._data = np.zeros((50, 50, 3), dtype=np.uint8)
        imaging = MagicMock(spec=ImagingManager)
        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(source_image, template_image, confidence=0.9)
        assert result is not None
        assert result.confidence == pytest.approx(0.95)
        assert result.region.x == 100
        assert result.region.y == 50

    def test_find_all(self, source_image: Image, template_image: Image) -> None:
        result_data = np.zeros((151, 251), dtype=np.float32)
        result_data[10, 20] = 0.95
        result_data[100, 150] = 0.92
        bt = source_image._backend.match_template
        bt.return_value = result_data  # type: ignore[attr-defined]
        template_image._data = np.zeros((50, 50, 3), dtype=np.uint8)
        imaging = MagicMock(spec=ImagingManager)
        matcher = TemplateMatcher(imaging)
        results = matcher.find_all(source_image, template_image, confidence=0.9)
        assert len(results) == 2
        assert results[0].confidence >= results[1].confidence

    def test_find_all_below_confidence(self, source_image: Image, template_image: Image) -> None:
        result_data = np.zeros((151, 251), dtype=np.float32)
        result_data[10, 20] = 0.5
        bt = source_image._backend.match_template
        bt.return_value = result_data  # type: ignore[attr-defined]
        template_image._data = np.zeros((50, 50, 3), dtype=np.uint8)
        imaging = MagicMock(spec=ImagingManager)
        matcher = TemplateMatcher(imaging)
        results = matcher.find_all(source_image, template_image, confidence=0.9)
        assert len(results) == 0

    def test_loads_template_from_path(self, source_image: Image) -> None:
        imaging = MagicMock(spec=ImagingManager)
        tmpl_img = Image(np.zeros((10, 10, 3), dtype=np.uint8), MagicMock())
        imaging.load.return_value = tmpl_img
        matcher = TemplateMatcher(imaging)
        bt = source_image._backend.match_template
        bt.return_value = np.zeros((191, 291), dtype=np.float32)  # type: ignore[attr-defined]
        result = matcher.find_best(source_image, Path("icon.png"), confidence=0.5)
        assert result is None
        imaging.load.assert_called_once_with(Path("icon.png"))
