"""Tests for imaging exception hierarchy."""

from __future__ import annotations

import pytest

from ugaf.core.exceptions import UGAFError
from ugaf.imaging.exceptions import (
    BackendNotAvailableError,
    ImageLoadError,
    ImageSaveError,
    ImagingError,
)


class TestImagingExceptions:
    def test_imaging_error_base(self) -> None:
        assert issubclass(ImagingError, UGAFError)

    def test_image_load_error(self) -> None:
        assert issubclass(ImageLoadError, ImagingError)

    def test_image_save_error(self) -> None:
        assert issubclass(ImageSaveError, ImagingError)

    def test_backend_not_available(self) -> None:
        assert issubclass(BackendNotAvailableError, ImagingError)

    def test_all_exceptions_raise(self) -> None:
        for exc_cls in (ImageLoadError, ImageSaveError, BackendNotAvailableError):
            with pytest.raises(ImagingError):
                raise exc_cls("test")
