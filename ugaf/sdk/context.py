"""Game context for UGAF game plugins."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ugaf.core.config import Config
from ugaf.core.di import DependencyContainer
from ugaf.core.event_bus import EventBus
from ugaf.core.logger import Logger

__all__ = [
    "GameContext",
]


@dataclass
class GameContext:
    """Context provided to every game plugin.

    Wires core framework services so that plugins can interact with
    configuration, logging, events, and other plugins.

    Attributes:
        config: Application configuration.
        logger: Structured logger instance.
        event_bus: Async publish/subscribe event bus.
        service_container: Dependency injection container.
        device_id: The specific device this plugin *instance* targets,
            when the plugin is one of several concurrent instances of
            the same automation bound to different devices (see
            :class:`~ugaf.plugins.manager.PluginManager`'s
            ``device_id``-parametrized methods). ``None`` for a
            single-instance plugin, in which case it should fall back
            to its own device-resolution logic (e.g. config, or
            ``DeviceManager.resolve_device()``).
        extra: Extension dictionary for additional services.

    """

    config: Config | dict[str, Any]
    logger: Logger | None = None
    event_bus: EventBus | None = None
    service_container: DependencyContainer | None = None
    device_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
