"""Abstract base class for UGAF game plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ugaf.sdk.context import GameContext
from ugaf.sdk.metadata import PluginMetadata

__all__ = [
    "GamePlugin",
]


class GamePlugin(ABC):
    """Abstract base class that every game plugin must implement.

    Subclasses must define :attr:`metadata` as a class-level
    :class:`~ugaf.sdk.metadata.PluginMetadata` and implement all
    lifecycle methods.

    Usage::

        class MyGame(GamePlugin):
            metadata = PluginMetadata(
                name="My Game",
                id="my_game",
                author="Me",
                version="1.0.0",
                description="A game plugin",
            )

            async def initialize(self, context: GameContext) -> None:
                self._context = context

            async def start(self) -> None: ...
            async def pause(self) -> None: ...
            async def resume(self) -> None: ...
            async def stop(self) -> None: ...
            async def shutdown(self) -> None: ...
            async def health(self) -> dict[str, Any]:
                return {"status": "healthy"}

    """

    metadata: PluginMetadata

    @abstractmethod
    async def initialize(self, context: GameContext) -> None:
        """Prepare the plugin for execution.

        Args:
            context: The game context providing access to framework
                services.

        """

    @abstractmethod
    async def start(self) -> None:
        """Begin the plugin's main activity."""

    @abstractmethod
    async def pause(self) -> None:
        """Temporarily suspend the plugin's activity."""

    @abstractmethod
    async def resume(self) -> None:
        """Resume after a pause."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the plugin's main activity."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release all resources. This is the terminal lifecycle step."""

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """Return the current health status of the plugin.

        Returns:
            A dictionary with at least a ``"status"`` key.

        """
