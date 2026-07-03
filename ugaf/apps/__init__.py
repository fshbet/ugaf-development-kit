"""Application Manager: reusable Android application lifecycle management.

Every automation that targets an installed Android app (a game, a
utility, anything) should go through :class:`ApplicationManager`
rather than issuing its own launch/foreground/stop commands — see
``games/shadow_fight_3/app.yaml`` for how a plugin declares its
target application as data.
"""

from __future__ import annotations

from ugaf.apps.manager import ApplicationManager
from ugaf.apps.types import AppDefinition, LaunchResult

__all__ = [
    "ApplicationManager",
    "AppDefinition",
    "LaunchResult",
]
