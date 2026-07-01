"""Tests for the notifications abstraction."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from ugaf.platform.exceptions import AdapterNotAvailableError
from ugaf.platform.notifications import WindowsNotificationProvider, _escape_powershell


def test_escape_powershell_escapes_quotes_and_backticks() -> None:
    assert _escape_powershell('He said "hi" `now`') == 'He said `"hi`" ``now``'


def test_notify_invokes_powershell_with_escaped_args() -> None:
    provider = WindowsNotificationProvider()
    with (
        patch("shutil.which", return_value="C:\\Windows\\powershell.exe"),
        patch("subprocess.run") as mock_run,
    ):
        provider.notify("Title", "Message", timeout=2.0)

    mock_run.assert_called_once()
    args, kwargs = mock_run.call_args
    command = args[0]
    assert command[0] == "C:\\Windows\\powershell.exe"
    assert "-NonInteractive" in command
    assert kwargs["check"] is True
    assert kwargs["timeout"] == pytest.approx(7.0)


def test_notify_raises_when_powershell_not_found() -> None:
    provider = WindowsNotificationProvider()
    with patch("shutil.which", return_value=None):
        with pytest.raises(AdapterNotAvailableError, match="powershell"):
            provider.notify("Title", "Message")


def test_notify_raises_on_called_process_error() -> None:
    provider = WindowsNotificationProvider()
    with (
        patch("shutil.which", return_value="powershell"),
        patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "powershell"),
        ),
    ):
        with pytest.raises(AdapterNotAvailableError, match="PowerShell notification failed"):
            provider.notify("Title", "Message")


def test_notify_raises_on_timeout() -> None:
    provider = WindowsNotificationProvider()
    with (
        patch("shutil.which", return_value="powershell"),
        patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired("powershell", 5.0),
        ),
    ):
        with pytest.raises(AdapterNotAvailableError, match="PowerShell notification failed"):
            provider.notify("Title", "Message")
