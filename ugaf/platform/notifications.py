"""Desktop notification abstraction."""

from __future__ import annotations

import shutil
import subprocess
from abc import ABC, abstractmethod

from ugaf.platform.exceptions import AdapterNotAvailableError

__all__ = [
    "NotificationProvider",
    "WindowsNotificationProvider",
]

_TOAST_SCRIPT_TEMPLATE = """
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.Visible = $true
$notify.ShowBalloonTip({timeout_ms}, "{title}", "{message}", `
    [System.Windows.Forms.ToolTipIcon]::Info)
Start-Sleep -Milliseconds {timeout_ms}
$notify.Dispose()
"""


def _escape_powershell(value: str) -> str:
    """Escape double quotes and backticks for safe interpolation into a PowerShell string."""
    return value.replace("`", "``").replace('"', '`"')


class NotificationProvider(ABC):
    """Abstract interface for showing desktop notifications."""

    @abstractmethod
    def notify(self, title: str, message: str, timeout: float = 5.0) -> None:
        """Display a notification.

        Args:
            title: Notification title.
            message: Notification body text.
            timeout: How long the notification should remain visible,
                in seconds.

        Raises:
            AdapterNotAvailableError: If the underlying OS mechanism
                is unavailable on this host.

        """


class WindowsNotificationProvider(NotificationProvider):
    """Notification provider using a Windows Forms balloon tip via PowerShell.

    Uses ``System.Windows.Forms.NotifyIcon``, which ships with every
    Windows installation that has the .NET Framework — no extra
    PowerShell module (e.g. ``BurntToast``) needs to be installed.
    """

    def notify(self, title: str, message: str, timeout: float = 5.0) -> None:
        """Show a balloon-tip notification by running a short PowerShell script.

        Raises:
            AdapterNotAvailableError: If ``powershell``/``pwsh`` is not
                on ``PATH`` or the script fails.

        """
        powershell = shutil.which("powershell") or shutil.which("pwsh")
        if powershell is None:
            raise AdapterNotAvailableError("Neither 'powershell' nor 'pwsh' was found on PATH")

        script = _TOAST_SCRIPT_TEMPLATE.format(
            timeout_ms=int(timeout * 1000),
            title=_escape_powershell(title),
            message=_escape_powershell(message),
        )
        try:
            subprocess.run(  # noqa: S603
                [powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                timeout=timeout + 5.0,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise AdapterNotAvailableError(f"PowerShell notification failed: {exc}") from exc
