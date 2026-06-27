"""Example Game — a reference plugin for the UGAF Game SDK."""

from __future__ import annotations

from typing import Any

from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata

metadata = PluginMetadata(
    name="Example Game",
    id="example_game",
    author="UGAF Team",
    version="1.0.0",
    description="A reference game plugin that verifies the Game SDK works correctly",
    supported_platforms=["windows", "linux"],
    minimum_framework_version="1.0.0",
    capabilities=[],  # No automation capabilities needed
    priority=100,
)


class ExampleGame(GamePlugin):
    """Reference implementation that logs lifecycle events.

    This plugin performs no game automation, screenshots, or AI.
    It simply exercises the full GamePlugin lifecycle to verify
    the SDK and plugin framework.

    """

    metadata = metadata

    def __init__(self) -> None:
        """Initialize the plugin state."""
        self._context: GameContext | None = None
        self._health_status: str = "created"

    async def initialize(self, context: GameContext) -> None:
        """Store the context and mark as initialized."""
        self._context = context
        self._health_status = "initialized"
        context.logger.info(
            "example_game.initialized",
            plugin=self.metadata.id,
        )

    async def start(self) -> None:
        """Begin the plugin lifecycle."""
        self._health_status = "running"
        if self._context is not None:
            self._context.logger.info(
                "example_game.started",
                plugin=self.metadata.id,
            )

    async def pause(self) -> None:
        """Pause the plugin."""
        self._health_status = "paused"
        if self._context is not None:
            self._context.logger.info(
                "example_game.paused",
                plugin=self.metadata.id,
            )

    async def resume(self) -> None:
        """Resume from paused state."""
        self._health_status = "running"
        if self._context is not None:
            self._context.logger.info(
                "example_game.resumed",
                plugin=self.metadata.id,
            )

    async def stop(self) -> None:
        """Stop the plugin."""
        self._health_status = "stopped"
        if self._context is not None:
            self._context.logger.info(
                "example_game.stopped",
                plugin=self.metadata.id,
            )

    async def shutdown(self) -> None:
        """Release all resources."""
        self._health_status = "shutdown"
        if self._context is not None:
            self._context.logger.info(
                "example_game.shutdown",
                plugin=self.metadata.id,
            )

    async def health(self) -> dict[str, Any]:
        """Return current health status."""
        return {
            "status": self._health_status,
            "plugin": self.metadata.id,
        }
