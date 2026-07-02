"""Shadow Fight 3 — thin plugin shell over the knowledge-driven automation stack.

All game-specific detail — moves, button positions, and combat
strategy — lives in data under ``knowledge/`` and ``strategies/`` in
this directory, loaded by :class:`~ugaf.automation.knowledge.KnowledgeBase`
and :class:`~ugaf.automation.strategy.StrategyEngine`. This plugin only
wires that data to a real device: connect, run the strategy loop via
:class:`~ugaf.automation.executor.Executor`, stop, report status. See
``README.md`` in this directory for the full architecture and how to
add a new move or strategy without touching this file.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from ugaf.automation.executor import Executor
from ugaf.automation.knowledge import KnowledgeBase
from ugaf.automation.strategy import Strategy, StrategyEngine
from ugaf.core.config import Config
from ugaf.imaging.manager import ImagingManager
from ugaf.input.manager import InputManager
from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.vision.adb_screenshot import AdbScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager

metadata = PluginMetadata(
    name="Shadow Fight 3",
    id="shadow_fight_3",
    author="UGAF Team",
    version="2.0.0",
    description=(
        "Knowledge-driven combat automation: moves and behaviour come from "
        "knowledge/ and strategies/ YAML, not Python."
    ),
    supported_platforms=["android"],
    minimum_framework_version="1.0.0",
    capabilities=[],
    priority=100,
)

_GAME_DIR = Path(__file__).parent


class ShadowFight3Game(GamePlugin):
    """Loads this game's knowledge/strategy and drives the executor loop."""

    metadata = metadata

    def __init__(self) -> None:
        """Load config and knowledge; nothing device-related happens yet."""
        self._context: GameContext | None = None
        self._health_status: str = "created"
        self._config = Config(_GAME_DIR / "config.yaml")
        self._knowledge = KnowledgeBase.load(_GAME_DIR / "knowledge")
        self._input: InputManager | None = None
        self._executor: Executor | None = None
        self._strategy_engine: StrategyEngine | None = None
        self._loop_task: asyncio.Task[None] | None = None
        self._running_event = asyncio.Event()
        self._cycle_count = 0
        self._last_moves: list[str] = []

    async def initialize(self, context: GameContext) -> None:
        """Store the context and mark as initialized."""
        self._context = context
        self._health_status = "initialized"
        if context.logger is not None:
            context.logger.info("shadow_fight_3.initialized")

    async def start(self) -> None:
        """Connect to the device, load the configured strategy, and start the loop."""
        assert self._context is not None
        logger = self._context.logger
        assert logger is not None
        container = self._context.service_container
        assert container is not None

        imaging = container.resolve(ImagingManager)

        self._input = InputManager(self._config)
        self._input.connect()

        device_id = self._config.get("input.adb.default_device")
        screenshot = ScreenshotManager(imaging=imaging)
        screenshot.connect_with(AdbScreenshotProvider(imaging, device_id=device_id))

        strategy_name = str(self._config.get("strategy", "balanced"))
        strategy = Strategy.load(_GAME_DIR / "strategies" / f"{strategy_name}.yaml")
        self._strategy_engine = StrategyEngine(strategy)
        self._executor = Executor(self._input, self._knowledge.controls)

        self._health_status = "running"
        self._running_event.set()
        self._cycle_count = 0
        self._loop_task = asyncio.create_task(self._combat_loop())
        logger.info(
            "shadow_fight_3.started",
            screen_size=self._input.screen_size,
            strategy=strategy_name,
        )

    async def pause(self) -> None:
        """Suspend the combat loop without tearing down the connection."""
        self._health_status = "paused"
        self._running_event.clear()
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info("shadow_fight_3.paused")

    async def resume(self) -> None:
        """Resume the combat loop."""
        self._health_status = "running"
        self._running_event.set()
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info("shadow_fight_3.resumed")

    async def stop(self) -> None:
        """Stop the combat loop and disconnect from the device."""
        self._health_status = "stopped"
        self._running_event.clear()
        if self._loop_task is not None:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
            self._loop_task = None
        if self._input is not None:
            self._input.disconnect()
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info(
                "shadow_fight_3.stopped", cycles_run=self._cycle_count
            )

    async def shutdown(self) -> None:
        """Release resources."""
        self._health_status = "shutdown"
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info("shadow_fight_3.shutdown")

    async def health(self) -> dict[str, Any]:
        """Return the plugin's health status and combat progress."""
        return {
            "status": self._health_status,
            "cycles_run": self._cycle_count,
            "last_moves": self._last_moves,
            "strategy": self._strategy_engine.name if self._strategy_engine else None,
        }

    # ------------------------------------------------------------------
    # Combat loop
    # ------------------------------------------------------------------

    async def _combat_loop(self) -> None:
        """Run combat cycles until cancelled or ``max_cycles`` is reached.

        Each cycle asks the :class:`StrategyEngine` which moves to run
        (data-driven), then hands each move's step sequence to the
        :class:`Executor` (generic, game-agnostic). This method
        contains no move names, coordinates, or combo logic itself.
        """
        assert self._context is not None and self._context.logger is not None
        assert self._strategy_engine is not None and self._executor is not None
        logger = self._context.logger
        strategy_engine = self._strategy_engine
        executor = self._executor
        max_cycles = self._config.get("max_cycles")

        try:
            while True:
                await self._running_event.wait()
                self._cycle_count += 1

                move_names = strategy_engine.select({"cycle": self._cycle_count})
                self._last_moves = move_names
                for name in move_names:
                    await executor.execute_move(self._knowledge.moves[name])

                logger.info(
                    "shadow_fight_3.cycle",
                    cycle=self._cycle_count,
                    moves=move_names,
                )

                if max_cycles is not None and self._cycle_count >= int(max_cycles):
                    logger.info("shadow_fight_3.max_cycles_reached", cycles=self._cycle_count)
                    return

                await asyncio.sleep(strategy_engine.cycle_interval)
        except asyncio.CancelledError:
            raise
