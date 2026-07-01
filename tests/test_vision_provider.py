"""Tests for the VisionProvider ABC."""

from __future__ import annotations

from typing import Any

import pytest

from ugaf.vision.provider import VisionProvider


class TestVisionProvider:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            VisionProvider()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class _ConcreteProvider(VisionProvider):
            def screenshot(self) -> None:  # type: ignore[override]
                return None

            def screenshot_region(self, region: object) -> None:  # type: ignore[override]
                return None

            def find_template(
                self, source: object, template: object, confidence: float = 0.9
            ) -> None:
                return None

            def find_all_templates(
                self, source: object, template: object, confidence: float = 0.9
            ) -> list[Any]:
                return []

            def detect_contours(
                self, image: object, min_area: int = 0, max_area: int = 0
            ) -> list[Any]:
                return []

            def pixel_matches(
                self, image: object, x: int, y: int, color: object, threshold: float = 30.0
            ) -> bool:
                return False

        provider = _ConcreteProvider()
        assert isinstance(provider, VisionProvider)
