"""Exception hierarchy for the imaging engine."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError

__all__ = [
    "BackendNotAvailableError",
    "ImageLoadError",
    "ImageSaveError",
    "ImagingError",
]


class ImagingError(UGAFError):
    """Base exception for all imaging engine errors."""


class ImageLoadError(ImagingError):
    """Raised when an image file cannot be loaded."""


class ImageSaveError(ImagingError):
    """Raised when an image file cannot be saved."""


class BackendNotAvailableError(ImagingError):
    """Raised when the requested imaging backend is not available."""
