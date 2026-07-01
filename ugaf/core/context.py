"""Application context for the UGAF framework."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ugaf.core.config import Config
from ugaf.core.di import DependencyContainer
from ugaf.core.event_bus import EventBus
from ugaf.core.health import HealthRegistry
from ugaf.core.logger import Logger
from ugaf.core.platform import PlatformInfo
from ugaf.plugins.manager import PluginManager

__all__ = [
    "AppContext",
    "ApplicationState",
]


@dataclass
class ApplicationState:
    """Mutable runtime state of the application.

    Attributes:
        phase: Current lifecycle phase string (e.g. ``"initialized"``,
            ``"started"``, ``"stopped"``).
        running: Whether the application is actively running.
        error: Most recent error message, if any.
        started_at: Unix timestamp of when ``start()`` was called.

    """

    phase: str = "created"
    running: bool = False
    error: str | None = None
    started_at: float | None = None


@dataclass
class AppContext:
    """Shared application context.

    Provides a single point of access to all core services.

    Attributes:
        config: Application configuration.
        logger: Structured logger instance.
        event_bus: Async publish/subscribe event bus.
        container: Dependency injection container.
        plugin_manager: SDK plugin discovery, validation, and lifecycle
            orchestration.
        health_registry: Health check registration.
        platform: Detected platform information.
        version: Framework version string.
        state: Mutable application runtime state.
        extra: Extension dictionary for Sprint 03+ modules.

    """

    config: Config
    logger: Logger
    event_bus: EventBus
    container: DependencyContainer
    plugin_manager: PluginManager
    health_registry: HealthRegistry
    platform: PlatformInfo
    version: str = "1.0.0a5"
    state: ApplicationState = field(default_factory=ApplicationState)
    extra: dict[str, Any] = field(default_factory=dict)
