"""Tests for the OpenCVBackend."""

from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ugaf.imaging.exceptions import BackendNotAvailableError, ImageLoadError, ImageSaveError


def _reset_cache() -> None:
    """Reset the OpenCV availability cache for testing."""
    import ugaf.imaging.opencv_backend as ob

    ob._LIBRARIES_AVAILABLE = None


def _make_backend() -> tuple[Any, MagicMock, ExitStack]:
    """Create an OpenCVBackend with a mocked cv2, keeping the mock active.

    Returns:
        A tuple of (backend, mock_cv2, exit_stack). The caller must call
        ``exit_stack.close()`` to clean up.
    """
    _reset_cache()
    mock_cv2 = MagicMock()
    stack = ExitStack()
    stack.enter_context(patch.dict("sys.modules", {"cv2": mock_cv2}))
    from ugaf.imaging.opencv_backend import OpenCVBackend

    backend = OpenCVBackend()
    return backend, mock_cv2, stack


class TestOpenCVBackend:
    def test_init_success(self) -> None:
        _reset_cache()
        mock_cv2 = MagicMock()
        with patch.dict("sys.modules", {"cv2": mock_cv2}):
            from ugaf.imaging.opencv_backend import OpenCVBackend

            backend = OpenCVBackend()
            assert backend is not None

    def test_init_failure(self) -> None:
        _reset_cache()
        with patch.dict("sys.modules", {"cv2": None}):
            with patch("importlib.import_module", side_effect=ImportError("no cv2")):
                with pytest.raises(BackendNotAvailableError):
                    from ugaf.imaging.opencv_backend import OpenCVBackend

                    OpenCVBackend()

    def test_load_image(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.imread.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = backend.load(Path("test.png"))
        assert data is not None
        stack.close()

    def test_load_image_failure(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.imread.return_value = None
        with pytest.raises(ImageLoadError):
            backend.load(Path("nonexistent.png"))
        stack.close()

    def test_save_image(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.imwrite.return_value = True
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        backend.save(data, Path("output.png"))
        mock_cv2.imwrite.assert_called_once()
        stack.close()

    def test_save_image_failure(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.imwrite.return_value = False
        with pytest.raises(ImageSaveError):
            backend.save(np.zeros((100, 200, 3), dtype=np.uint8), Path("output.png"))
        stack.close()

    def test_width_height(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        assert backend.width(data) == 200
        assert backend.height(data) == 100
        stack.close()

    def test_crop(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.crop(data, 10, 10, 50, 50)
        assert result.shape == (50, 50, 3)
        stack.close()

    def test_grayscale(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.cvtColor.return_value = np.zeros((100, 200), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.grayscale(data)
        assert result.shape == (100, 200)
        mock_cv2.cvtColor.assert_called_once()
        stack.close()

    def test_rotate(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.getRotationMatrix2D.return_value = np.eye(2, 3)
        mock_cv2.warpAffine.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.rotate(data, 90.0)
        assert result is not None
        stack.close()

    def test_resize(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.resize.return_value = np.zeros((50, 100, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.resize(data, 100, 50)
        assert result is not None
        stack.close()

    def test_blur(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.GaussianBlur.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.blur(data, ksize=5)
        assert result is not None
        stack.close()

    def test_threshold(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.threshold.return_value = (None, np.zeros((100, 200), dtype=np.uint8))
        data = np.zeros((100, 200), dtype=np.uint8)
        result = backend.threshold(data)
        assert result is not None
        stack.close()

    def test_flip(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.flip.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.flip(data, direction="horizontal")
        assert result is not None
        stack.close()

    def test_match_template(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.matchTemplate.return_value = np.zeros((51, 151), dtype=np.float32)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        tmpl = np.zeros((50, 50, 3), dtype=np.uint8)
        result = backend.match_template(data, tmpl)
        assert result is not None
        stack.close()

    def test_invert(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.bitwise_not.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.invert(data)
        assert result is not None
        stack.close()

    def test_scale(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.resize.return_value = np.zeros((200, 400, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.scale(data, 2.0)
        assert result is not None
        stack.close()

    def test_draw_rectangle(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.rectangle.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.draw_rectangle(data, 10, 10, 50, 50)
        assert result is not None
        stack.close()

    def test_draw_circle(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.circle.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.draw_circle(data, 100, 50, 20)
        assert result is not None
        stack.close()

    def test_draw_text(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.putText.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.draw_text(data, "hello", 10, 20)
        assert result is not None
        stack.close()

    def test_normalize(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.normalize.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.normalize(data)
        assert result is not None
        stack.close()

    def test_sharpen(self) -> None:
        backend, mock_cv2, stack = _make_backend()
        mock_cv2.filter2D.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        result = backend.sharpen(data)
        assert result is not None
        stack.close()
