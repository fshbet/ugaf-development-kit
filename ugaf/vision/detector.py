"""Feature detection for finding visual elements."""

from __future__ import annotations

from dataclasses import dataclass

from ugaf.imaging.image import Image
from ugaf.vision.region import Region

__all__ = [
    "DetectedFeature",
    "FeatureDetector",
]


@dataclass(frozen=True)
class DetectedFeature:
    """A visual feature detected in an image.

    Attributes:
        region: The bounding region of the feature.
        confidence: Detection confidence (0.0 – 1.0).
        label: Optional label describing the feature.

    """

    region: Region
    confidence: float
    label: str = ""


class FeatureDetector:
    """Detects visual features (contours, blobs, lines) in images.

    Wraps OpenCV feature-detection primitives exposed through the
    imaging backend.

    Usage::

        detector = FeatureDetector()
        buttons = detector.find_contours(
            screenshot,
            min_area=100,
            max_area=5000,
        )
        for btn in buttons:
            click(btn.region.center)

    """

    def find_contours(
        self,
        image: Image,
        min_area: int = 0,
        max_area: int = 0,
        approx_poly: bool = True,
    ) -> list[DetectedFeature]:
        """Find contours in the image.

        Args:
            image: The source image (will be converted to grayscale
                internally).
            min_area: Minimum contour area (0 = no filter).
            max_area: Maximum contour area (0 = no filter).
            approx_poly: Whether to approximate contour polygons.

        Returns:
            A list of :class:`DetectedFeature` instances.

        Raises:
            DetectionError: If contour detection fails.

        """
        import cv2

        gray = image.grayscale()
        data = gray.as_contiguous_array()
        edged = cv2.Canny(data, 50, 150)

        mode = cv2.CHAIN_APPROX_SIMPLE if approx_poly else cv2.CHAIN_APPROX_NONE
        result = cv2.findContours(edged, cv2.RETR_EXTERNAL, mode)
        contours = result[0] if len(result) == 2 else result[1]

        features: list[DetectedFeature] = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area > 0 and area < min_area:
                continue
            if max_area > 0 and area > max_area:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            region = Region(x=int(x), y=int(y), width=int(w), height=int(h))
            features.append(DetectedFeature(region=region, confidence=1.0))

        return features

    def find_blobs(
        self,
        image: Image,
        min_area: int = 100,
        max_area: int = 5000,
        circularity: float = 0.5,
    ) -> list[DetectedFeature]:
        """Find blobs (connected regions) in the image.

        Args:
            image: The source image (will be converted to grayscale
                internally).
            min_area: Minimum blob area.
            max_area: Maximum blob area.
            circularity: Minimum circularity (0.0 – 1.0).

        Returns:
            A list of :class:`DetectedFeature` instances.

        Raises:
            DetectionError: If blob detection fails.

        """
        import cv2

        gray = image.grayscale()
        data = gray.as_contiguous_array()

        params = cv2.SimpleBlobDetector_Params()  # type: ignore[attr-defined]
        params.filterByArea = True
        params.minArea = min_area
        params.maxArea = max_area
        params.filterByCircularity = True
        params.minCircularity = circularity

        detector = cv2.SimpleBlobDetector_create(params)  # type: ignore[attr-defined]
        keypoints = detector.detect(data)

        features: list[DetectedFeature] = []
        for kp in keypoints:
            x = int(kp.pt[0] - kp.size / 2)
            y = int(kp.pt[1] - kp.size / 2)
            w = int(kp.size)
            h = int(kp.size)
            region = Region(x=x, y=y, width=w, height=h)
            features.append(DetectedFeature(region=region, confidence=kp.response))

        return features

    def find_lines(
        self,
        image: Image,
        rho: float = 1.0,
        theta: float = 1.0,
        threshold: int = 100,
    ) -> list[DetectedFeature]:
        """Find straight lines in the image using the Hough transform.

        Args:
            image: The source image (will be converted to grayscale
                internally).
            rho: Distance resolution in pixels.
            theta: Angle resolution in degrees.
            threshold: Accumulator threshold.

        Returns:
            A list of :class:`DetectedFeature` instances (each with an
            approximate bounding region).

        Raises:
            DetectionError: If line detection fails.

        """
        import math

        import cv2

        gray = image.grayscale()
        data = gray.as_contiguous_array()
        edges = cv2.Canny(data, 50, 150)
        lines = cv2.HoughLines(edges, rho, math.radians(theta), threshold)

        features: list[DetectedFeature] = []
        if lines is not None:
            for line in lines:
                rho_val, theta_val = line[0]
                x0 = int(rho_val * math.cos(theta_val))
                y0 = int(rho_val * math.sin(theta_val))
                region = Region(
                    x=max(0, x0 - 5),
                    y=max(0, y0 - 5),
                    width=10,
                    height=10,
                )
                features.append(DetectedFeature(region=region, confidence=1.0))

        return features
