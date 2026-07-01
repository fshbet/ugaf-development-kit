"""Tests for the clipboard abstraction.

``WindowsClipboardProvider`` is exercised against the real Win32
clipboard (round-trip write/read) since that is the most reliable way
to verify the ``ctypes`` handle/restype plumbing is actually correct
(a prior version of this code silently corrupted 64-bit handles by
relying on ``ctypes``' default ``c_int`` restype).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from ugaf.platform.clipboard import WindowsClipboardProvider
from ugaf.platform.exceptions import AdapterNotAvailableError

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="requires ctypes.windll")


def test_write_then_read_round_trip() -> None:
    provider = WindowsClipboardProvider()
    provider.write_text("ugaf-platform-clipboard-test")
    assert provider.read_text() == "ugaf-platform-clipboard-test"


def test_write_then_read_unicode_round_trip() -> None:
    provider = WindowsClipboardProvider()
    provider.write_text("héllo wörld — 你好")
    assert provider.read_text() == "héllo wörld — 你好"


def test_read_open_clipboard_failure_raises() -> None:
    provider = WindowsClipboardProvider()
    with patch("ctypes.windll.user32.OpenClipboard", return_value=0):
        with pytest.raises(AdapterNotAvailableError, match="Unable to open"):
            provider.read_text()


def test_write_global_alloc_failure_raises() -> None:
    provider = WindowsClipboardProvider()
    with patch("ctypes.windll.kernel32.GlobalAlloc", return_value=None):
        with pytest.raises(AdapterNotAvailableError, match="GlobalAlloc failed"):
            provider.write_text("x")


def test_require_ctypes_raises_when_windll_missing() -> None:
    provider = WindowsClipboardProvider()
    with patch("ctypes.windll", None, create=True):
        with pytest.raises(AdapterNotAvailableError, match="requires Windows"):
            provider.read_text()
