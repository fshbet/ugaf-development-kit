"""Plugin event topic constants for UGAF game plugins."""

from __future__ import annotations

__all__ = [
    "PLUGIN_LOADED",
    "PLUGIN_INITIALIZED",
    "PLUGIN_STARTED",
    "PLUGIN_PAUSED",
    "PLUGIN_STOPPED",
    "PLUGIN_SHUTDOWN",
    "PLUGIN_FAILED",
]

PLUGIN_LOADED = "plugin.loaded"
"""Published when a plugin is discovered and registered."""

PLUGIN_INITIALIZED = "plugin.initialized"
"""Published when a plugin is successfully initialized."""

PLUGIN_STARTED = "plugin.started"
"""Published when a plugin transitions to RUNNING state."""

PLUGIN_PAUSED = "plugin.paused"
"""Published when a plugin transitions to PAUSED state."""

PLUGIN_STOPPED = "plugin.stopped"
"""Published when a plugin transitions to STOPPED state."""

PLUGIN_SHUTDOWN = "plugin.shutdown"
"""Published when a plugin transitions to SHUTDOWN state."""

PLUGIN_FAILED = "plugin.failed"
"""Published when a plugin encounters an error during any lifecycle step."""
