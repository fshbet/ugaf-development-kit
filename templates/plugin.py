"""Template game plugin for the UGAF Game SDK.

Copy this directory to ``games/<your_game_id>/`` and rename ``id``,
``name``, and the class below. See ``games/example_game/`` for a
minimal reference implementation and ``GAME_PLUGIN_SDK.md`` for the
full lifecycle contract.
"""

from __future__ import annotations

from typing import Any

from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata

metadata = PluginMetadata(
    name="My Game",
    id="my_game",
    author="Your Name",
    version="1.0.0",
    description="A short description of what this plugin automates.",
    supported_platforms=["windows", "linux", "android"],
    minimum_framework_version="1.0.0",
    capabilities=[],
    priority=100,
)


class MyGame(GamePlugin):
    """Template plugin — replace with real automation logic."""

    metadata = metadata

    def __init__(self) -> None:
        """Initialize plugin state."""
        self._context: GameContext | None = None

    async def initialize(self, context: GameContext) -> None:
        """Store the context and prepare any resources."""
        self._context = context

    async def start(self) -> None:
        """Begin the plugin's main activity."""

    async def stop(self) -> None:
        """Stop the plugin's main activity."""

    async def shutdown(self) -> None:
        """Release all resources."""

    async def health(self) -> dict[str, Any]:
        """Return the current health status."""
        return {"status": "healthy"}
