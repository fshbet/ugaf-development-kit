"""OCR (Optical Character Recognition) stub.

No OCR engine is implemented yet.  This module exists as a placeholder
for future integration with Tesseract, EasyOCR, or similar libraries.
"""

from __future__ import annotations

from ugaf.imaging.image import Image
from ugaf.vision.exceptions import OCRError

__all__ = [
    "OCRProvider",
]


class OCRProvider:
    """Placeholder OCR provider.

    All methods raise :class:`OCRError` because no OCR engine is
    configured.  This preserves the API shape for future implementation.

    """

    def extract_text(self, image: Image) -> str:
        """Extract text from an image.

        Args:
            image: The image to perform OCR on.

        Returns:
            The extracted text string.

        Raises:
            OCRError: Always — OCR is not yet implemented.

        """
        raise OCRError("OCR is not implemented in this release")

    def find_text(
        self,
        image: Image,
        text: str,
    ) -> list[tuple[int, int, int, int]]:
        """Find bounding boxes of *text* in *image*.

        Args:
            image: The image to search.
            text: The text string to locate.

        Returns:
            A list of bounding box tuples ``(x, y, w, h)``.

        Raises:
            OCRError: Always — OCR is not yet implemented.

        """
        raise OCRError("OCR is not implemented in this release")
