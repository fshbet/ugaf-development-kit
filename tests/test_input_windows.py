"""Tests for the Windows input provider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ugaf.input.exceptions import ConnectionFailedError
from ugaf.input.windows import WindowsInputProvider


@pytest.fixture
def provider() -> WindowsInputProvider:
    return WindowsInputProvider()


@pytest.fixture
def connected_provider() -> WindowsInputProvider:
    p = WindowsInputProvider()
    p._connected = True
    p._pyautogui = MagicMock()
    p._keyboard = MagicMock()
    p._mouse = MagicMock()
    return p


def test_initial_state(provider: WindowsInputProvider) -> None:
    assert provider.is_connected() is False


def test_disconnect_when_not_connected(provider: WindowsInputProvider) -> None:
    provider.disconnect()
    assert provider.is_connected() is False


def test_connect_success(provider: WindowsInputProvider) -> None:
    import sys as _sys

    with (
        patch("ugaf.input.windows._check_libraries", return_value=True),
        patch.dict(
            _sys.modules,
            {"pyautogui": MagicMock(), "keyboard": MagicMock(), "mouse": MagicMock()},
        ),
    ):
        provider.connect()
    assert provider.is_connected() is True


@patch("ugaf.input.windows._check_libraries", return_value=False)
def test_connect_missing_libraries(mock_check: MagicMock, provider: WindowsInputProvider) -> None:
    with pytest.raises(ConnectionFailedError, match="not installed"):
        provider.connect()


def test_disconnect_clears_state(connected_provider: WindowsInputProvider) -> None:
    connected_provider.disconnect()
    assert connected_provider.is_connected() is False
    assert connected_provider._pyautogui is None


def test_click(connected_provider: WindowsInputProvider) -> None:
    connected_provider.click(100, 200)
    connected_provider._pyautogui.click.assert_called_once_with(100, 200, button="left")


def test_click_right_button(connected_provider: WindowsInputProvider) -> None:
    connected_provider.click(100, 200, button="right")
    connected_provider._pyautogui.click.assert_called_once_with(100, 200, button="right")


def test_double_click(connected_provider: WindowsInputProvider) -> None:
    connected_provider.double_click(50, 60)
    connected_provider._pyautogui.doubleClick.assert_called_once_with(50, 60)


def test_right_click(connected_provider: WindowsInputProvider) -> None:
    connected_provider.right_click(30, 40)
    connected_provider._pyautogui.rightClick.assert_called_once_with(30, 40)


def test_move_mouse(connected_provider: WindowsInputProvider) -> None:
    connected_provider.move_mouse(200, 300, duration=0.5)
    connected_provider._pyautogui.moveTo.assert_called_once_with(200, 300, duration=0.5)


def test_drag(connected_provider: WindowsInputProvider) -> None:
    connected_provider.drag(0, 0, 100, 200, duration=0.3)
    connected_provider._pyautogui.moveTo.assert_called_once_with(0, 0)
    connected_provider._mouse.drag.assert_called_once_with(100, 200, duration=0.3)


def test_scroll(connected_provider: WindowsInputProvider) -> None:
    connected_provider.scroll(-3, x=100, y=200)
    connected_provider._pyautogui.scroll.assert_called_once_with(-3, x=100, y=200)


def test_key_down(connected_provider: WindowsInputProvider) -> None:
    connected_provider.key_down("ctrl")
    connected_provider._keyboard.press.assert_called_once_with("ctrl")


def test_key_up(connected_provider: WindowsInputProvider) -> None:
    connected_provider.key_up("shift")
    connected_provider._keyboard.release.assert_called_once_with("shift")


def test_press_key(connected_provider: WindowsInputProvider) -> None:
    connected_provider.press_key("enter")
    connected_provider._keyboard.send.assert_called_once_with("enter")


def test_type_text(connected_provider: WindowsInputProvider) -> None:
    connected_provider.type_text("hello world")
    connected_provider._keyboard.write.assert_called_once_with("hello world", delay=0.0)


def test_hotkey(connected_provider: WindowsInputProvider) -> None:
    connected_provider.hotkey("ctrl", "c")
    connected_provider._keyboard.send.assert_called_once_with("ctrl+c")


def test_wait(connected_provider: WindowsInputProvider) -> None:
    with patch("ugaf.input.windows.time.sleep") as mock_sleep:
        connected_provider.wait(1.5)
        mock_sleep.assert_called_once_with(1.5)


def test_take_screenshot(connected_provider: WindowsInputProvider) -> None:
    connected_provider.take_screenshot()
    connected_provider._pyautogui.screenshot.assert_called_once_with()


def test_take_screenshot_to_path(connected_provider: WindowsInputProvider) -> None:
    mock_img = MagicMock()
    connected_provider._pyautogui.screenshot.return_value = mock_img
    result = connected_provider.take_screenshot(path="/tmp/test.png")
    assert result is None
    mock_img.save.assert_called_once_with("/tmp/test.png")


def test_screen_size(connected_provider: WindowsInputProvider) -> None:
    connected_provider._pyautogui.size.return_value = (1920, 1080)
    assert connected_provider.screen_size == (1920, 1080)


def test_operations_raise_when_disconnected(provider: WindowsInputProvider) -> None:
    with pytest.raises(ConnectionFailedError, match="not connected"):
        provider.click(0, 0)
    with pytest.raises(ConnectionFailedError, match="not connected"):
        provider.move_mouse(0, 0)
    with pytest.raises(ConnectionFailedError, match="not connected"):
        provider.screen_size
