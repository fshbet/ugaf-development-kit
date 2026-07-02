"""Tests for MockInputProvider."""

from __future__ import annotations

from ugaf.input.mock import MockInputProvider


class TestLifecycle:
    def test_connect_and_disconnect(self) -> None:
        provider = MockInputProvider()
        assert provider.is_connected() is False
        provider.connect()
        assert provider.is_connected() is True
        provider.disconnect()
        assert provider.is_connected() is False

    def test_default_screen_size(self) -> None:
        provider = MockInputProvider()
        assert provider.screen_size == (1080, 1920)

    def test_configured_screen_size(self) -> None:
        provider = MockInputProvider({"screen_width": 400, "screen_height": 800})
        assert provider.screen_size == (400, 800)


class TestActionRecording:
    def test_click_is_recorded_not_performed(self) -> None:
        provider = MockInputProvider()
        provider.click(10, 20)
        assert provider.calls == [("click", (10, 20, "left"))]

    def test_drag_is_recorded(self) -> None:
        provider = MockInputProvider()
        provider.drag(0, 0, 100, 100, duration=0.5)
        assert provider.calls == [("drag", (0, 0, 100, 100, 0.5))]

    def test_type_text_is_recorded(self) -> None:
        provider = MockInputProvider()
        provider.type_text("hello")
        assert provider.calls == [("type_text", ("hello",))]

    def test_take_screenshot_returns_none(self) -> None:
        provider = MockInputProvider()
        assert provider.take_screenshot() is None

    def test_wait_does_not_actually_sleep(self) -> None:
        import time

        provider = MockInputProvider()
        start = time.perf_counter()
        provider.wait(5.0)
        assert time.perf_counter() - start < 1.0
        assert provider.calls == [("wait", (5.0,))]

    def test_multiple_actions_accumulate_in_order(self) -> None:
        provider = MockInputProvider()
        provider.click(1, 2)
        provider.drag(1, 2, 3, 4)
        provider.type_text("x")
        assert [c[0] for c in provider.calls] == ["click", "drag", "type_text"]
