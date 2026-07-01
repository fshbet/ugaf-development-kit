"""Template matching and image search utilities."""

from __future__ import annotations

from pathlib import Path

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.region import Region

__all__ = [
    "TemplateMatcher",
    "MatchResult",
]


class MatchResult:
    """Result of a single template match.

    Attributes:
        region: The matched region on the source image.
        confidence: Match confidence score (0.0 – 1.0).

    """

    def __init__(self, region: Region, confidence: float) -> None:
        """Initialise a match result.

        Args:
            region: The matched region on the source image.
            confidence: Match confidence score (0.0 – 1.0).

        """
        self._region = region
        self._confidence = confidence

    @property
    def region(self) -> Region:
        """Return the matched region."""
        return self._region

    @property
    def confidence(self) -> float:
        """Return the match confidence score."""
        return self._confidence

    @property
    def center(self) -> tuple[int, int]:
        """Return the centre point of the matched region."""
        return (self._region.center_x, self._region.center_y)

    def __repr__(self) -> str:
        """Return a human-readable representation."""
        return f"MatchResult(region={self._region}, confidence={self._confidence:.3f})"


class TemplateMatcher:
    """Performs template matching on images.

    Wraps the imaging engine's ``match_template`` backend with a
    higher-level API that returns :class:`MatchResult` objects.

    Usage::

        matcher = TemplateMatcher(imaging)
        results = matcher.find_all(
            source=screenshot,
            template=Path("icon.png"),
            confidence=0.85,
        )
        for result in results:
            click(result.center)

    """

    def __init__(
        self,
        imaging: ImagingManager,
        default_method: str = "ccorr_normed",
        default_confidence: float = 0.9,
    ) -> None:
        """Initialise the matcher.

        Args:
            imaging: An :class:`~ugaf.imaging.manager.ImagingManager`
                instance for image loading and backend access.
            default_method: Default template matching method.
            default_confidence: Default confidence threshold.

        """
        self._imaging = imaging
        self._default_method = default_method
        self._default_confidence = default_confidence

    def find_all(
        self,
        source: Image,
        template: Image | Path | str,
        method: str | None = None,
        confidence: float | None = None,
    ) -> list[MatchResult]:
        """Find all occurrences of *template* in *source*.

        Args:
            source: The image to search within.
            template: The template image to find (an :class:`Image`,
                or a path to load).
            method: Matching method (``"ccorr_normed"``,
                ``"ccoeff_normed"``, ``"sqdiff_normed"``).
            confidence: Minimum confidence threshold (0.0 – 1.0).

        Returns:
            A list of :class:`MatchResult` instances, one per match.

        Raises:
            TemplateMatchError: If matching fails.

        """
        import numpy

        method = method if method is not None else self._default_method
        confidence = confidence if confidence is not None else self._default_confidence

        tmpl = self._resolve_template(template)
        result_data = source.match_template(tmpl, method=method)

        th, tw = tmpl._data.shape[:2]

        if method in ("sqdiff", "sqdiff_normed"):
            loc = numpy.where(result_data <= 1.0 - confidence)
        else:
            loc = numpy.where(result_data >= confidence)

        raw_matches: list[MatchResult] = []
        for pt_y, pt_x in zip(*loc, strict=False):
            if tw == 0 or th == 0:
                break
            region = Region(x=int(pt_x), y=int(pt_y), width=tw, height=th)
            conf = float(result_data[pt_y, pt_x])
            if method in ("sqdiff", "sqdiff_normed"):
                conf = 1.0 - conf if conf <= 1.0 else 0.0
            raw_matches.append(MatchResult(region=region, confidence=conf))

        raw_matches.sort(key=lambda m: m.confidence, reverse=True)
        return _non_maximum_suppression(raw_matches, overlap_threshold=0.5)

    def find_best(
        self,
        source: Image,
        template: Image | Path | str,
        method: str | None = None,
        confidence: float | None = None,
    ) -> MatchResult | None:
        """Find the best match of *template* in *source*.

        Args:
            source: The image to search within.
            template: The template image to find.
            method: Matching method.
            confidence: Minimum confidence threshold.

        Returns:
            A :class:`MatchResult` for the best match, or ``None`` if
            no match meets the confidence threshold.

        Raises:
            TemplateMatchError: If matching fails.

        """
        matches = self.find_all(source, template, method=method, confidence=confidence)
        return matches[0] if matches else None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_template(self, template: Image | Path | str) -> Image:
        """Resolve a template argument to an :class:`Image`."""
        if isinstance(template, Image):
            return template
        return self._imaging.load(template)


def _non_maximum_suppression(
    matches: list[MatchResult],
    overlap_threshold: float = 0.5,
) -> list[MatchResult]:
    """Remove duplicate matches whose regions overlap significantly.

    Keeps only the highest-confidence match from each cluster of
    overlapping regions.

    Args:
        matches: Sorted list of matches (highest confidence first).
        overlap_threshold: Maximum allowed IoU ratio before a
            lower-confidence match is suppressed.

    Returns:
        Filtered list of matches (highest confidence first).

    """
    kept: list[MatchResult] = []
    for match in matches:
        suppressed = False
        for kept_match in kept:
            inter = match.region.intersection(kept_match.region)
            if inter is not None:
                area_a = match.region.area
                area_b = kept_match.region.area
                denom = area_a + area_b - inter.area
                iou = inter.area / denom if denom > 0 else 0.0
                if iou > overlap_threshold:
                    suppressed = True
                    break
        if not suppressed:
            kept.append(match)
    return kept
