"""Tests for the ScreenshotProvider ABC."""

from __future__ import annotations

import pytest

from ugaf.vision.screenshot import ScreenshotProvider


class TestScreenshotProvider:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            ScreenshotProvider()  # type: ignore[abstract]

    def test_concrete_subclass(self) -> None:
        class _ConcreteScreenshotProvider(ScreenshotProvider):
            def capture_full(self):  # type: ignore[no-untyped-def]
                return None

            def capture_region(self, region):  # type: ignore[no-untyped-def]
                return None

            def capture_game_window(self, window_title):  # type: ignore[no-untyped-def]
                return None

        provider = _ConcreteScreenshotProvider()
        assert isinstance(provider, ScreenshotProvider)
