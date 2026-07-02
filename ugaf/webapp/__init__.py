"""UGAF web control panel — a browser-based UI over the existing framework.

The Core Engine (``ugaf.core``, ``ugaf.device``, ``ugaf.plugins``) is
unchanged by this package; ``ugaf.webapp`` is purely a thin FastAPI
layer that lets a user detect devices, view the live screen, tap,
swipe, enter text, and run plugins without writing code or using ADB
directly.
"""

from __future__ import annotations

from ugaf.webapp.server import create_app
from ugaf.webapp.session import AppSession

__all__ = [
    "AppSession",
    "create_app",
]
