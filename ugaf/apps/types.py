"""Typed application metadata and launch results.

An :class:`AppDefinition` is the data-driven counterpart to
hand-writing package names and activities in Python — every
automation names the Android application it targets in an
``app.yaml`` file (see ``games/shadow_fight_3/app.yaml`` for a worked
example), loaded here into a typed object.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

__all__ = [
    "AppDefinition",
    "LaunchResult",
]


@dataclass(frozen=True)
class AppDefinition:
    """An Android application's identity and launch/shutdown behaviour.

    Attributes:
        name: Human-readable application name (shown in the UI).
        package: Android package name (e.g. ``com.nekki.shadowfight3``).
        launch_activity: Explicit ``package/activity`` component to
            start. When ``None``, :class:`~ugaf.apps.manager.ApplicationManager`
            launches via the app's launcher intent instead (works for
            any installed app without knowing its activity name).
        orientation: Documented expected orientation
            (``"portrait"``/``"landscape"``); informational only today
            — no rotation is enforced.
        launch_timeout: Seconds to wait for the app to reach the
            foreground before retrying.
        launch_retries: Additional launch attempts after the first
            failure.
        expected_startup_templates: Template names (relative to the
            plugin's ``knowledge/templates/`` directory) that confirm
            the app has reached a known-good startup screen — checked
            by the caller via ``VisionManager.wait_until_visible``,
            not by :class:`ApplicationManager` itself. Empty means
            "foreground package match is sufficient."
        expected_resolution: Optional ``(width, height)`` sanity check
            against the device's actual screen size.
        shutdown_behavior: ``"leave_running"`` (default — never
            force-stop the app) or ``"force_stop"`` (stop it when the
            automation stops).

    """

    name: str
    package: str
    launch_activity: str | None = None
    orientation: str | None = None
    launch_timeout: float = 15.0
    launch_retries: int = 2
    expected_startup_templates: tuple[str, ...] = ()
    expected_resolution: tuple[int, int] | None = None
    shutdown_behavior: str = "leave_running"

    @classmethod
    def load(cls, path: Path) -> AppDefinition:
        """Load an application definition from an ``app.yaml`` file."""
        data = yaml.safe_load(path.read_text()) or {}
        resolution = data.get("expected_resolution")
        return cls(
            name=str(data["name"]),
            package=str(data["package"]),
            launch_activity=data.get("launch_activity"),
            orientation=data.get("orientation"),
            launch_timeout=float(data.get("launch_timeout", 15.0)),
            launch_retries=int(data.get("launch_retries", 2)),
            expected_startup_templates=tuple(data.get("expected_startup_templates") or ()),
            expected_resolution=(int(resolution[0]), int(resolution[1]))
            if resolution
            else None,
            shutdown_behavior=str(data.get("shutdown_behavior", "leave_running")),
        )


@dataclass(frozen=True)
class LaunchResult:
    """Outcome of an :class:`~ugaf.apps.manager.ApplicationManager` launch attempt.

    Attributes:
        success: Whether the app reached the foreground within budget.
        package: The package that was targeted.
        foreground_package: Whatever package was actually in the
            foreground when launch resolution finished (may differ
            from ``package`` on failure — useful for diagnosing "a
            system dialog stole focus" style failures).
        attempts: Number of launch attempts made (1 = succeeded first try).
        elapsed: Total seconds spent across all attempts.
        error: Human-readable failure reason, or ``None`` on success.

    """

    success: bool
    package: str
    foreground_package: str | None
    attempts: int
    elapsed: float
    error: str | None = field(default=None)
