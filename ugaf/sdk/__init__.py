"""Game SDK for building UGAF-compatible game plugins."""

from ugaf.sdk.capabilities import Capability
from ugaf.sdk.context import GameContext
from ugaf.sdk.events import (
    PLUGIN_FAILED,
    PLUGIN_INITIALIZED,
    PLUGIN_LOADED,
    PLUGIN_PAUSED,
    PLUGIN_SHUTDOWN,
    PLUGIN_STARTED,
    PLUGIN_STOPPED,
)
from ugaf.sdk.exceptions import GameSDKError, PluginStateError, PluginValidationError
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState

__all__ = [
    "Capability",
    "GameContext",
    "GamePlugin",
    "GameSDKError",
    "GameState",
    "PLUGIN_FAILED",
    "PLUGIN_INITIALIZED",
    "PLUGIN_LOADED",
    "PLUGIN_PAUSED",
    "PLUGIN_SHUTDOWN",
    "PLUGIN_STARTED",
    "PLUGIN_STOPPED",
    "PluginMetadata",
    "PluginStateError",
    "PluginValidationError",
]
