"""Tests for the abstract InputProvider base class."""

from __future__ import annotations

import pytest

from ugaf.input.provider import InputProvider


class _ConcreteProvider(InputProvider):
    """Minimal concrete implementation for testing the ABC."""

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool:
        return False

    def click(self, x: int, y: int, button: str = "left") -> None: ...
    def double_click(self, x: int, y: int) -> None: ...
    def right_click(self, x: int, y: int) -> None: ...
    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.0) -> None: ...
    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None: ...
    def key_down(self, key: str) -> None: ...
    def key_up(self, key: str) -> None: ...
    def press_key(self, key: str) -> None: ...
    def type_text(self, text: str) -> None: ...
    def hotkey(self, *keys: str) -> None: ...
    @property
    def screen_size(self) -> tuple[int, int]:
        return (0, 0)

    def wait(self, seconds: float) -> None: ...
    def take_screenshot(self, path: str | None = None) -> bytes | None:
        return None


def test_cannot_instantiate_abstract_class() -> None:
    with pytest.raises(TypeError):
        InputProvider()  # type: ignore[abstract]


def test_concrete_provider_is_valid() -> None:
    provider = _ConcreteProvider()
    assert isinstance(provider, InputProvider)
    assert provider.is_connected() is False
    assert provider.take_screenshot() is None
