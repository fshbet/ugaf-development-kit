"""Image operation constants for the imaging engine."""

from __future__ import annotations

__all__ = [
    "Interpolation",
    "MatchMethod",
    "FlipDirection",
]

Interpolation = str
"""Interpolation method for resizing.

Supported values: ``"linear"``, ``"cubic"``, ``"nearest"``, ``"lanczos"``.
"""

MatchMethod = str
"""Template matching method.

Supported values: ``"ccorr"``, ``"ccorr_normed"``, ``"ccoeff"``,
``"ccoeff_normed"``, ``"sqdiff"``, ``"sqdiff_normed"``.
"""

FlipDirection = str
"""Flip direction.

Supported values: ``"horizontal"``, ``"vertical"``.
"""
