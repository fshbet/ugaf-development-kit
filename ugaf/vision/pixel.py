"""Pixel-level screen analysis."""

from __future__ import annotations

from dataclasses import dataclass

from ugaf.imaging.image import Image
from ugaf.vision.color import Color, is_color_match
from ugaf.vision.exceptions import PixelMatchError
from ugaf.vision.region import Region

__all__ = [
    "Pixel",
    "scan_pixels",
    "wait_for_pixel",
]


@dataclass(frozen=True)
class Pixel:
    """Immutable pixel representation.

    Attributes:
        x: X coordinate.
        y: Y coordinate.
        color: The colour at this pixel.

    """

    x: int
    y: int
    color: Color


def scan_pixels(
    image: Image,
    region: Region | None = None,
) -> list[Pixel]:
    """Scan all pixels in the given image (or region thereof).

    Args:
        image: The source image.
        region: Optional sub-region to scan.  Scans the full image if
            ``None``.

    Returns:
        A list of :class:`Pixel` instances.

    Raises:
        PixelMatchError: If the region is out of bounds.

    """
    data = image.data
    h, w = data.shape[:2]

    rx = region.x if region is not None else 0
    ry = region.y if region is not None else 0
    rw = region.width if region is not None else w
    rh = region.height if region is not None else h

    if rx < 0 or ry < 0 or rx + rw > w or ry + rh > h:
        raise PixelMatchError(
            f"Region ({rx}, {ry}, {rw}, {rh}) is out of bounds for image of size ({w}, {h})"
        )

    sub = data[ry : ry + rh, rx : rx + rw]
    pixels: list[Pixel] = []
    for dy in range(rh):
        for dx in range(rw):
            b, g, r = sub[dy, dx]
            pixels.append(Pixel(x=rx + dx, y=ry + dy, color=Color(r=int(r), g=int(g), b=int(b))))
    return pixels


def wait_for_pixel(
    image: Image,
    color: Color,
    x: int,
    y: int,
    threshold: float = 30.0,
) -> bool:
    """Check whether a specific pixel matches the expected colour.

    Args:
        image: The source image.
        color: Expected colour.
        x: X coordinate.
        y: Y coordinate.
        threshold: Colour distance threshold.

    Returns:
        ``True`` if the pixel colour matches.

    Raises:
        PixelMatchError: If the coordinate is out of bounds.

    """
    data = image.data
    h, w = data.shape[:2]
    if x < 0 or y < 0 or x >= w or y >= h:
        raise PixelMatchError(
            f"Coordinate ({x}, {y}) is out of bounds for image of size ({w}, {h})"
        )

    b, g, r = data[y, x]
    actual = Color(r=int(r), g=int(g), b=int(b))
    return is_color_match(actual, color, threshold=threshold)
