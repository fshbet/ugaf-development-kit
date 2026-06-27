"""Core framework modules for the Universal Game Automation Framework."""

from ugaf.core.bootstrap import Application
from ugaf.core.config import Config, ConfigError
from ugaf.core.event_bus import Event, EventBus, EventBusError, EventHandler
from ugaf.core.exceptions import ApplicationError, UGAFError
from ugaf.core.logger import Logger, LoggerConfig, get_logger
from ugaf.core.plugin_loader import (
    PluginInfo,
    PluginLoader,
    PluginLoaderError,
    PluginManifest,
)

__all__ = [
    "Application",
    "ApplicationError",
    "Config",
    "ConfigError",
    "Event",
    "EventBus",
    "EventBusError",
    "EventHandler",
    "Logger",
    "LoggerConfig",
    "PluginInfo",
    "PluginLoader",
    "PluginLoaderError",
    "PluginManifest",
    "UGAFError",
    "get_logger",
]
