"""Tests for the input engine type definitions."""

from __future__ import annotations

import pytest

from ugaf.input.types import Button, Key, Point


def test_point_creation() -> None:
    p = Point(100, 200)
    assert p.x == 100
    assert p.y == 200


def test_point_is_frozen() -> None:
    p = Point(1, 2)
    import dataclasses

    assert dataclasses.is_dataclass(p)
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.x = 99  # type: ignore[misc]


def test_point_equality() -> None:
    assert Point(10, 20) == Point(10, 20)
    assert Point(10, 20) != Point(30, 40)


def test_button_type_alias() -> None:
    b: Button = "left"
    assert b == "left"
    b = "right"
    assert b == "right"
    b = "middle"
    assert b == "middle"


def test_key_type_alias() -> None:
    k: Key = "enter"
    assert k == "enter"
    k = "space"
    assert k == "space"
