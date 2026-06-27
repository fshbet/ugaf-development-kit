"""Plugin metadata for UGAF game plugins."""

from __future__ import annotations

from dataclasses import dataclass, field

from ugaf.sdk.capabilities import Capability

__all__ = [
    "PluginMetadata",
]


@dataclass(frozen=True)
class PluginMetadata:
    """Immutable metadata describing a game plugin.

    Attributes:
        name: Human-readable display name.
        id: Unique identifier for the plugin.
        author: Plugin author or organisation.
        version: Semantic version string.
        description: Short description of the plugin.
        supported_platforms: List of supported OS platforms.
        minimum_framework_version: Minimum UGAF framework version
            required.
        capabilities: List of capabilities the plugin provides.
        priority: Load priority (lower = loaded first).

    """

    name: str
    id: str
    author: str
    version: str
    description: str = ""
    supported_platforms: list[str] = field(default_factory=list)
    minimum_framework_version: str = "1.0.0"
    capabilities: list[Capability] = field(default_factory=list)
    priority: int = 100
