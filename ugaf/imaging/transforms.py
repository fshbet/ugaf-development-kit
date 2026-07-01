"""Transform constants for the imaging engine."""

from __future__ import annotations

__all__ = [
    "TransformType",
]

TransformType = str
"""Image transform type.

Supported values: ``"crop"``, ``"resize"``, ``"rotate"``, ``"scale"``,
``"flip"``.
"""
