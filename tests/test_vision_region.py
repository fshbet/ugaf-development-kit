"""Tests for the Region dataclass."""

from __future__ import annotations

import pytest

from ugaf.vision.region import Region


class TestRegion:
    def test_attributes(self) -> None:
        r = Region(x=10, y=20, width=100, height=200)
        assert r.x == 10
        assert r.y == 20
        assert r.width == 100
        assert r.height == 200

    def test_right(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.right == 110

    def test_bottom(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.bottom == 220

    def test_center_x(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.center_x == 60

    def test_center_y(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.center_y == 120

    def test_area(self) -> None:
        r = Region(0, 0, 100, 200)
        assert r.area == 20000

    def test_contains_inside(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.contains(50, 100) is True

    def test_contains_edge(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.contains(10, 20) is True
        assert r.contains(110, 220) is True

    def test_contains_outside(self) -> None:
        r = Region(10, 20, 100, 200)
        assert r.contains(0, 0) is False
        assert r.contains(200, 300) is False

    def test_immutable(self) -> None:
        r = Region(1, 2, 3, 4)
        with pytest.raises(AttributeError):
            r.x = 99  # type: ignore[misc]

    def test_intersection_overlapping(self) -> None:
        a = Region(0, 0, 100, 100)
        b = Region(50, 50, 100, 100)
        result = a.intersection(b)
        assert result is not None
        assert result == Region(50, 50, 50, 50)

    def test_intersection_contained(self) -> None:
        a = Region(0, 0, 100, 100)
        b = Region(10, 10, 20, 20)
        result = a.intersection(b)
        assert result is not None
        assert result == Region(10, 10, 20, 20)

    def test_intersection_no_overlap(self) -> None:
        a = Region(0, 0, 100, 100)
        b = Region(200, 200, 100, 100)
        result = a.intersection(b)
        assert result is None

    def test_intersection_touching_edge(self) -> None:
        a = Region(0, 0, 100, 100)
        b = Region(100, 0, 100, 100)
        result = a.intersection(b)
        assert result is None

    def test_equality(self) -> None:
        a = Region(1, 2, 3, 4)
        b = Region(1, 2, 3, 4)
        assert a == b

    def test_hashable(self) -> None:
        s = {Region(1, 2, 3, 4)}
        assert Region(1, 2, 3, 4) in s
