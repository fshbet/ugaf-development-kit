"""Filter constants and helpers for the imaging engine."""

from __future__ import annotations

__all__ = [
    "FilterType",
]

FilterType = str
"""Image filter type.

Supported values: ``"blur"``, ``"sharpen"``, ``"normalize"``,
``"threshold"``, ``"grayscale"``, ``"invert"``.
"""
