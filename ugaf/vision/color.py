"""Colour representation and comparison utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ugaf.vision.exceptions import ColorMatchError

__all__ = [
    "Color",
    "color_distance",
    "is_color_match",
]


@dataclass(frozen=True)
class Color:
    """Immutable RGB colour.

    Attributes:
        r: Red channel (0–255).
        g: Green channel (0–255).
        b: Blue channel (0–255).

    """

    r: int
    g: int
    b: int

    def to_bgr(self) -> tuple[int, int, int]:
        """Return the colour as a BGR tuple (for OpenCV compatibility)."""
        return (self.b, self.g, self.r)

    @classmethod
    def from_hex(cls, hex_str: str) -> Color:
        """Create a Color from a hex string (e.g. ``"#FF00FF"``).

        Args:
            hex_str: Hex colour string with optional ``#`` prefix.

        Returns:
            A new :class:`Color` instance.

        Raises:
            ColorMatchError: If the string cannot be parsed.

        """
        cleaned = hex_str.lstrip("#")
        if len(cleaned) != 6:
            raise ColorMatchError(f"Cannot parse colour from {hex_str!r}: expected 6 hex digits")
        try:
            r = int(cleaned[0:2], 16)
            g = int(cleaned[2:4], 16)
            b = int(cleaned[4:6], 16)
        except ValueError as exc:
            raise ColorMatchError(f"Cannot parse colour from {hex_str!r}: {exc}") from exc
        return cls(r, g, b)

    @classmethod
    def from_bgr(cls, bgr: tuple[int, int, int]) -> Color:
        """Create a Color from a BGR tuple.

        Args:
            bgr: BGR tuple (blue, green, red).

        Returns:
            A new :class:`Color` instance.

        """
        return cls(r=bgr[2], g=bgr[1], b=bgr[0])


def color_distance(a: Color, b: Color) -> float:
    """Compute Euclidean RGB distance between two colours.

    Args:
        a: First colour.
        b: Second colour.

    Returns:
        Euclidean distance in RGB space (0.0 – ~441.0).

    """
    dr = a.r - b.r
    dg = a.g - b.g
    db = a.b - b.b
    return math.sqrt(dr * dr + dg * dg + db * db)


def is_color_match(a: Color, b: Color, threshold: float = 30.0) -> bool:
    """Check whether two colours match within a distance threshold.

    Args:
        a: First colour.
        b: Second colour.
        threshold: Maximum allowed RGB distance.

    Returns:
        ``True`` if the colours are considered a match.

    """
    return color_distance(a, b) <= threshold
