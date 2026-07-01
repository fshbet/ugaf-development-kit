"""Tests for the Image class."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.imaging.types import ImageSize


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock(spec=ImageBackend)
    backend.width.return_value = 200
    backend.height.return_value = 100
    return backend


@pytest.fixture
def sample_image(mock_backend: MagicMock) -> Image:
    data = np.zeros((100, 200, 3), dtype=np.uint8)
    return Image(data, mock_backend)


class TestImageProperties:
    def test_width(self, sample_image: Image, mock_backend: MagicMock) -> None:
        assert sample_image.width == 200
        mock_backend.width.assert_called_once()

    def test_height(self, sample_image: Image, mock_backend: MagicMock) -> None:
        assert sample_image.height == 100
        mock_backend.height.assert_called_once()

    def test_size(self, sample_image: Image) -> None:
        assert sample_image.size == ImageSize(width=200, height=100)

    def test_data(self, sample_image: Image) -> None:
        np.testing.assert_array_equal(sample_image.data, np.zeros((100, 200, 3), dtype=np.uint8))


class TestImageGeometry:
    def test_crop(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.crop.return_value = np.zeros((50, 50, 3), dtype=np.uint8)
        result = sample_image.crop(10, 10, 50, 50)
        assert isinstance(result, Image)
        mock_backend.crop.assert_called_once_with(sample_image._data, 10, 10, 50, 50)

    def test_resize(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.resize.return_value = np.zeros((50, 100, 3), dtype=np.uint8)
        result = sample_image.resize(100, 50)
        assert isinstance(result, Image)
        mock_backend.resize.assert_called_once_with(
            sample_image._data, 100, 50, interpolation="linear"
        )

    def test_rotate(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.rotate.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.rotate(90.0)
        assert isinstance(result, Image)
        mock_backend.rotate.assert_called_once_with(sample_image._data, 90.0)

    def test_scale(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.scale.return_value = np.zeros((200, 400, 3), dtype=np.uint8)
        result = sample_image.scale(2.0)
        assert isinstance(result, Image)
        mock_backend.scale.assert_called_once_with(sample_image._data, 2.0)

    def test_flip(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.flip.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.flip("horizontal")
        assert isinstance(result, Image)
        mock_backend.flip.assert_called_once_with(sample_image._data, direction="horizontal")


class TestImageFilters:
    def test_blur(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.blur.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.blur(ksize=5)
        assert isinstance(result, Image)
        mock_backend.blur.assert_called_once_with(sample_image._data, ksize=5)

    def test_sharpen(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.sharpen.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.sharpen()
        assert isinstance(result, Image)
        mock_backend.sharpen.assert_called_once()

    def test_normalize(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.normalize.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.normalize()
        assert isinstance(result, Image)
        mock_backend.normalize.assert_called_once()

    def test_threshold(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.threshold.return_value = np.zeros((100, 200), dtype=np.uint8)
        result = sample_image.threshold(thresh=128, maxval=255)
        assert isinstance(result, Image)
        mock_backend.threshold.assert_called_once_with(sample_image._data, thresh=128, maxval=255)

    def test_grayscale(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.grayscale.return_value = np.zeros((100, 200), dtype=np.uint8)
        result = sample_image.grayscale()
        assert isinstance(result, Image)
        mock_backend.grayscale.assert_called_once()

    def test_invert(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.invert.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.invert()
        assert isinstance(result, Image)
        mock_backend.invert.assert_called_once()


class TestImageDrawing:
    def test_draw_rectangle(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.draw_rectangle.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.draw_rectangle(10, 10, 50, 50)
        assert isinstance(result, Image)
        mock_backend.draw_rectangle.assert_called_once()

    def test_draw_circle(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.draw_circle.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.draw_circle(100, 50, 20)
        assert isinstance(result, Image)
        mock_backend.draw_circle.assert_called_once()

    def test_draw_text(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.draw_text.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        result = sample_image.draw_text("hello", 10, 20)
        assert isinstance(result, Image)
        mock_backend.draw_text.assert_called_once()


class TestImageMatch:
    def test_match_template(self, sample_image: Image, mock_backend: MagicMock) -> None:
        result_data = np.zeros((51, 151), dtype=np.float32)
        result_data[25, 75] = 0.95
        mock_backend.match_template.return_value = result_data
        tmpl_data = np.zeros((50, 50, 3), dtype=np.uint8)
        tmpl_backend = MagicMock(spec=ImageBackend)
        template = Image(tmpl_data, tmpl_backend)
        results = sample_image.match(template, confidence=0.9)
        assert isinstance(results, list)

    def test_match_no_result(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.match_template.return_value = np.zeros((51, 151), dtype=np.float32)
        tmpl = Image(np.zeros((50, 50, 3), dtype=np.uint8), MagicMock(spec=ImageBackend))
        results = sample_image.match(tmpl, confidence=0.9)
        assert results == []


class TestImageImmutability:
    def test_operations_return_new(self, sample_image: Image, mock_backend: MagicMock) -> None:
        mock_backend.crop.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        mock_backend.grayscale.return_value = np.zeros((10, 10), dtype=np.uint8)
        original_data = sample_image._data
        _ = sample_image.crop(0, 0, 10, 10).grayscale()
        assert sample_image._data is original_data


class TestImageSave:
    def test_save(self, sample_image: Image, mock_backend: MagicMock) -> None:
        sample_image.save("output.png")
        mock_backend.save.assert_called_once_with(sample_image._data, "output.png")
