"""Generic action executor: turns move sequences into real input calls.

The executor understands only generic verbs (``tap``, ``move``,
``hold``, ``wait``) — it has no knowledge of any specific game. A
game's :class:`~ugaf.automation.knowledge.KnowledgeBase` describes
moves in terms of these verbs, so no game ever needs a custom
executor.
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ugaf.automation.knowledge import ControlLayout, MoveDefinition
    from ugaf.input.manager import InputManager

__all__ = [
    "DIRECTIONS",
    "Executor",
]

# Unit vectors for the 8 directions a "move" step may name, matching a
# standard 8-way analog joystick.
DIRECTIONS: dict[str, tuple[float, float]] = {
    "right": (1.0, 0.0),
    "left": (-1.0, 0.0),
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
    "up_right": (math.sqrt(0.5), -math.sqrt(0.5)),
    "up_left": (-math.sqrt(0.5), -math.sqrt(0.5)),
    "down_right": (math.sqrt(0.5), math.sqrt(0.5)),
    "down_left": (-math.sqrt(0.5), math.sqrt(0.5)),
}

_STEP_DELAY = 0.15


class Executor:
    """Executes generic action steps against a connected :class:`InputManager`."""

    def __init__(self, input_manager: InputManager, controls: ControlLayout) -> None:
        """Bind the executor to an input device and its control layout."""
        self._input = input_manager
        self._controls = controls

    async def execute_move(self, move: MoveDefinition) -> None:
        """Run every step in *move*'s sequence, in order."""
        for step in move.sequence:
            await self._execute_step(step)

    async def _execute_step(self, step: dict[str, Any]) -> None:
        if "wait" in step:
            await asyncio.sleep(float(step["wait"]))
            return
        if "tap" in step:
            self._tap_button(step["tap"])
        elif "move" in step:
            self._tap_joystick(step["move"])
        elif "hold" in step:
            spec = step["hold"]
            target = spec["button"] if isinstance(spec, dict) else spec
            duration = float(spec.get("duration", 0.5)) if isinstance(spec, dict) else 0.5
            self._hold_button(target, duration)
        else:
            raise ValueError(f"Unknown executor step: {step!r}")
        await asyncio.sleep(_STEP_DELAY)

    def _screen_size(self) -> tuple[int, int]:
        size = self._input.screen_size
        if size is None:
            raise RuntimeError("InputManager has no detected screen size; connect() first")
        return size

    def _tap_button(self, name: str) -> None:
        x, y = self._controls.button_point(name, self._screen_size())
        self._input.click(x, y)

    def _tap_joystick(self, direction: str) -> None:
        x, y = self._controls.joystick_point(DIRECTIONS[direction], self._screen_size())
        self._input.click(x, y)

    def _hold_button(self, name: str, duration: float) -> None:
        # Plain ADB `input` has no press-and-hold primitive for a
        # single point; approximate a hold with a zero-distance drag,
        # which does keep the touch down for `duration` before release.
        x, y = self._controls.button_point(name, self._screen_size())
        self._input.drag(x, y, x, y, duration=duration)
