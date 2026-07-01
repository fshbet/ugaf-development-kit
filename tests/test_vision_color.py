"""Tests for the Color dataclass and colour utilities."""

from __future__ import annotations

import pytest

from ugaf.vision.color import Color, color_distance, is_color_match
from ugaf.vision.exceptions import ColorMatchError


class TestColor:
    def test_attributes(self) -> None:
        c = Color(r=255, g=128, b=0)
        assert c.r == 255
        assert c.g == 128
        assert c.b == 0

    def test_to_bgr(self) -> None:
        c = Color(r=255, g=128, b=0)
        assert c.to_bgr() == (0, 128, 255)

    def test_from_hex(self) -> None:
        c = Color.from_hex("#FF8000")
        assert c == Color(r=255, g=128, b=0)

    def test_from_hex_no_hash(self) -> None:
        c = Color.from_hex("FF8000")
        assert c == Color(r=255, g=128, b=0)

    def test_from_hex_invalid_length(self) -> None:
        with pytest.raises(ColorMatchError):
            Color.from_hex("#FFF")

    def test_from_hex_invalid_chars(self) -> None:
        with pytest.raises(ColorMatchError):
            Color.from_hex("#ZZZZZZ")

    def test_from_bgr(self) -> None:
        c = Color.from_bgr((0, 128, 255))
        assert c == Color(r=255, g=128, b=0)

    def test_immutable(self) -> None:
        c = Color(1, 2, 3)
        with pytest.raises(AttributeError):
            c.r = 99  # type: ignore[misc]

    def test_equality(self) -> None:
        assert Color(1, 2, 3) == Color(1, 2, 3)
        assert Color(1, 2, 3) != Color(3, 2, 1)


class TestColorDistance:
    def test_identical(self) -> None:
        assert color_distance(Color(0, 0, 0), Color(0, 0, 0)) == 0.0

    def test_black_white(self) -> None:
        d = color_distance(Color(0, 0, 0), Color(255, 255, 255))
        assert d == pytest.approx(441.67, rel=0.01)

    def test_partial(self) -> None:
        d = color_distance(Color(100, 0, 0), Color(0, 0, 0))
        assert d == 100.0


class TestIsColorMatch:
    def test_exact_match(self) -> None:
        assert is_color_match(Color(100, 100, 100), Color(100, 100, 100)) is True

    def test_within_threshold(self) -> None:
        assert is_color_match(Color(100, 100, 100), Color(110, 100, 100), threshold=15) is True

    def test_beyond_threshold(self) -> None:
        assert is_color_match(Color(100, 100, 100), Color(200, 100, 100), threshold=50) is False

    def test_custom_threshold(self) -> None:
        assert is_color_match(Color(0, 0, 0), Color(50, 0, 0), threshold=60) is True
        assert is_color_match(Color(0, 0, 0), Color(50, 0, 0), threshold=40) is False
