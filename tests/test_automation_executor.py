"""Tests for ugaf.automation.executor: Executor / generic action steps."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ugaf.automation.executor import DIRECTIONS, Executor
from ugaf.automation.knowledge import ControlLayout, MoveDefinition

pytestmark = pytest.mark.asyncio

_SCREEN_SIZE = (1000, 2000)


def _make_input_manager() -> MagicMock:
    mgr = MagicMock()
    mgr.screen_size = _SCREEN_SIZE
    return mgr


def _make_controls() -> ControlLayout:
    return ControlLayout(
        buttons={"punch": (0.9, 0.5), "kick": (0.1, 0.9)},
        joystick_center=(0.2, 0.8),
        joystick_radius=0.1,
    )


async def test_tap_step_clicks_resolved_button_coordinates() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="jab", sequence=[{"tap": "punch"}])

    await executor.execute_move(move)

    mgr.click.assert_called_once_with(round(0.9 * 1000), round(0.5 * 2000))


async def test_move_step_taps_joystick_direction() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="advance", sequence=[{"move": "right"}])

    await executor.execute_move(move)

    dx, dy = DIRECTIONS["right"]
    expected_x = round(0.2 * 1000 + dx * 0.1 * 1000)
    expected_y = round(0.8 * 2000 + dy * 0.1 * 1000)
    mgr.click.assert_called_once_with(expected_x, expected_y)


async def test_hold_step_drags_zero_distance_for_duration() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(
        name="heavy", sequence=[{"hold": {"button": "kick", "duration": 0.6}}]
    )

    await executor.execute_move(move)

    x, y = round(0.1 * 1000), round(0.9 * 2000)
    mgr.drag.assert_called_once_with(x, y, x, y, duration=0.6)


async def test_wait_step_does_not_touch_input_manager() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="pause", sequence=[{"wait": 0.01}])

    await executor.execute_move(move)

    mgr.click.assert_not_called()
    mgr.drag.assert_not_called()


async def test_multi_step_move_executes_all_steps_in_order() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="combo", sequence=[{"tap": "punch"}, {"tap": "kick"}])

    await executor.execute_move(move)

    assert mgr.click.call_count == 2


async def test_unknown_step_raises_value_error() -> None:
    mgr = _make_input_manager()
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="bad", sequence=[{"unknown_verb": "x"}])

    with pytest.raises(ValueError, match="Unknown executor step"):
        await executor.execute_move(move)


async def test_raises_without_detected_screen_size() -> None:
    mgr = _make_input_manager()
    mgr.screen_size = None
    executor = Executor(mgr, _make_controls())
    move = MoveDefinition(name="jab", sequence=[{"tap": "punch"}])

    with pytest.raises(RuntimeError, match="screen size"):
        await executor.execute_move(move)
