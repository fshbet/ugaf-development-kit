"""Region definition for screen area analysis."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Region",
]


@dataclass(frozen=True)
class Region:
    """Immutable rectangular region on the screen.

    Attributes:
        x: Left edge X coordinate.
        y: Top edge Y coordinate.
        width: Region width in pixels.
        height: Region height in pixels.

    """

    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        """Return the right edge X coordinate."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Return the bottom edge Y coordinate."""
        return self.y + self.height

    @property
    def center_x(self) -> int:
        """Return the centre X coordinate."""
        return self.x + self.width // 2

    @property
    def center_y(self) -> int:
        """Return the centre Y coordinate."""
        return self.y + self.height // 2

    @property
    def area(self) -> int:
        """Return the total pixel area."""
        return self.width * self.height

    def contains(self, px: int, py: int) -> bool:
        """Check whether a pixel coordinate lies inside this region.

        Args:
            px: Pixel X coordinate.
            py: Pixel Y coordinate.

        Returns:
            ``True`` if the pixel is inside the region.

        """
        return self.x <= px <= self.right and self.y <= py <= self.bottom

    def intersection(self, other: Region) -> Region | None:
        """Compute the intersection of two regions.

        Args:
            other: Another region.

        Returns:
            A new :class:`Region` representing the overlapping area, or
            ``None`` if the regions do not intersect.

        """
        ix = max(self.x, other.x)
        iy = max(self.y, other.y)
        ir = min(self.right, other.right)
        ib = min(self.bottom, other.bottom)
        if ix >= ir or iy >= ib:
            return None
        return Region(ix, iy, ir - ix, ib - iy)
