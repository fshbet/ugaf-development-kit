"""Type definitions for the imaging engine."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ImageSize",
]


@dataclass(frozen=True)
class ImageSize:
    """Immutable image dimensions.

    Attributes:
        width: Image width in pixels.
        height: Image height in pixels.

    """

    width: int
    height: int
