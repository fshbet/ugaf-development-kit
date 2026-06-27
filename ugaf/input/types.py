"""Type definitions for the input engine."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Button",
    "Key",
    "Point",
]

Button = str
"""Mouse button name (``"left"``, ``"right"``, ``"middle"``)."""

Key = str
"""Keyboard key name (``"enter"``, ``"space"``, ``"a"``, etc.)."""


@dataclass(frozen=True)
class Point:
    """A 2D screen coordinate.

    Attributes:
        x: Horizontal pixel position.
        y: Vertical pixel position.

    """

    x: int
    y: int
