"""Tests for the OCR stub module."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from ugaf.imaging.backend import ImageBackend
from ugaf.imaging.image import Image
from ugaf.vision.exceptions import OCRError
from ugaf.vision.ocr import OCRProvider


@pytest.fixture
def sample_image() -> Image:
    backend = MagicMock(spec=ImageBackend)
    data = np.zeros((100, 100, 3), dtype=np.uint8)
    return Image(data, backend)


class TestOCRProvider:
    def test_extract_text_raises(self, sample_image: Image) -> None:
        provider = OCRProvider()
        with pytest.raises(OCRError, match="not implemented"):
            provider.extract_text(sample_image)

    def test_find_text_raises(self, sample_image: Image) -> None:
        provider = OCRProvider()
        with pytest.raises(OCRError, match="not implemented"):
            provider.find_text(sample_image, "hello")
