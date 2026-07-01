"""Tests for imaging type definitions."""

from __future__ import annotations

import pytest

from ugaf.imaging.types import ImageSize


class TestImageSize:
    def test_attributes(self) -> None:
        s = ImageSize(width=1920, height=1080)
        assert s.width == 1920
        assert s.height == 1080

    def test_immutable(self) -> None:
        s = ImageSize(100, 200)
        with pytest.raises(AttributeError):
            s.width = 999  # type: ignore[misc]

    def test_equality(self) -> None:
        assert ImageSize(100, 200) == ImageSize(100, 200)
        assert ImageSize(100, 200) != ImageSize(200, 100)

    def test_hashable(self) -> None:
        s = {ImageSize(1, 2)}
        assert ImageSize(1, 2) in s
