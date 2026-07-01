"""Tests for the ImagingManager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.exceptions import ImageLoadError
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager


class TestImagingManager:
    def test_creates_with_explicit_backend(self) -> None:
        backend = MagicMock(spec=ImageBackend)
        manager = ImagingManager(backend=backend)
        assert manager.backend is backend

    @patch("ugaf.imaging.opencv_backend.OpenCVBackend")
    def test_creates_default_backend(self, mock_opencv: MagicMock) -> None:
        backend = MagicMock(spec=ImageBackend)
        mock_opencv.return_value = backend
        manager = ImagingManager()
        assert manager.backend is backend

    @patch("ugaf.imaging.opencv_backend.OpenCVBackend")
    def test_load(self, mock_opencv: MagicMock) -> None:
        backend = MagicMock(spec=ImageBackend)
        mock_opencv.return_value = backend
        data = np.zeros((100, 200, 3), dtype=np.uint8)
        backend.load.return_value = data
        manager = ImagingManager()
        img = manager.load(Path("test.png"))
        assert isinstance(img, Image)
        backend.load.assert_called_once_with(Path("test.png"))

    @patch("ugaf.imaging.opencv_backend.OpenCVBackend")
    def test_from_bytes(self, mock_opencv: MagicMock) -> None:
        backend = MagicMock(spec=ImageBackend)
        mock_opencv.return_value = backend
        manager = ImagingManager()
        img_bytes = b"fake_png_bytes"
        with patch("numpy.frombuffer") as mock_np:
            mock_np.return_value = np.array([1, 2, 3], dtype=np.uint8)
            with patch("cv2.imdecode") as mock_decode:
                mock_decode.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
                img = manager.from_bytes(img_bytes)
        assert isinstance(img, Image)

    def test_from_bytes_failure(self) -> None:
        backend = MagicMock(spec=ImageBackend)
        manager = ImagingManager(backend=backend)
        with patch("numpy.frombuffer") as mock_np:
            mock_np.return_value = np.array([1, 2, 3], dtype=np.uint8)
            with patch("cv2.imdecode") as mock_decode:
                mock_decode.return_value = None
                with pytest.raises(ImageLoadError):
                    manager.from_bytes(b"bad_bytes")
