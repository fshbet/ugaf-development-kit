"""Tests for ugaf.automation.knowledge: KnowledgeBase/MoveDefinition/ControlLayout."""

from __future__ import annotations

from pathlib import Path

import pytest

from ugaf.automation.knowledge import ControlLayout, KnowledgeBase, MoveDefinition


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_loads_moves_with_full_metadata(tmp_path: Path) -> None:
    _write(
        tmp_path / "moves.yaml",
        """
moves:
  jab:
    sequence:
      - tap: punch
      - tap: punch
    cooldown: 0.5
    damage: 10
    shadow_cost: 0
    range: melee
    startup: 0.1
    recovery: 0.2
    priority: 3
    tags: [combo, melee]
""",
    )
    _write(tmp_path / "buttons.yaml", "controls: {}\n")

    kb = KnowledgeBase.load(tmp_path)
    jab = kb.moves["jab"]
    assert isinstance(jab, MoveDefinition)
    assert jab.sequence == [{"tap": "punch"}, {"tap": "punch"}]
    assert jab.cooldown == 0.5
    assert jab.damage == 10
    assert jab.range == "melee"
    assert jab.startup == 0.1
    assert jab.recovery == 0.2
    assert jab.priority == 3
    assert jab.tags == ("combo", "melee")


def test_moves_default_metadata_when_omitted(tmp_path: Path) -> None:
    _write(tmp_path / "moves.yaml", "moves:\n  tap_once:\n    sequence:\n      - tap: punch\n")
    _write(tmp_path / "buttons.yaml", "controls: {}\n")

    kb = KnowledgeBase.load(tmp_path)
    move = kb.moves["tap_once"]
    assert move.cooldown == 0.0
    assert move.damage == 0.0
    assert move.tags == ()


def test_loads_button_and_analog_controls(tmp_path: Path) -> None:
    _write(tmp_path / "moves.yaml", "moves: {}\n")
    _write(
        tmp_path / "buttons.yaml",
        """
controls:
  joystick:
    type: analog
    center: { x: 0.1, y: 0.8 }
    radius: 0.05
  punch:
    type: button
    position: { x: 0.9, y: 0.7 }
""",
    )

    kb = KnowledgeBase.load(tmp_path)
    assert kb.controls.buttons == {"punch": (0.9, 0.7)}
    assert kb.controls.joystick_center == (0.1, 0.8)
    assert kb.controls.joystick_radius == 0.05


class TestControlLayoutResolution:
    def test_button_point_scales_by_screen_size(self) -> None:
        layout = ControlLayout(
            buttons={"punch": (0.5, 0.25)}, joystick_center=None, joystick_radius=0.0
        )
        assert layout.button_point("punch", (1000, 2000)) == (500, 500)

    def test_button_point_raises_for_unknown_button(self) -> None:
        layout = ControlLayout(buttons={}, joystick_center=None, joystick_radius=0.0)
        with pytest.raises(KeyError):
            layout.button_point("missing", (1000, 2000))

    def test_joystick_point_applies_direction_and_radius(self) -> None:
        layout = ControlLayout(buttons={}, joystick_center=(0.1, 0.8), joystick_radius=0.1)
        x, y = layout.joystick_point((1.0, 0.0), (1000, 2000))
        assert x == round(0.1 * 1000 + 0.1 * 1000)
        assert y == round(0.8 * 2000)

    def test_joystick_point_raises_without_joystick(self) -> None:
        layout = ControlLayout(buttons={}, joystick_center=None, joystick_radius=0.0)
        with pytest.raises(KeyError):
            layout.joystick_point((1.0, 0.0), (1000, 2000))


def test_shadow_fight_3_knowledge_loads_from_real_files() -> None:
    kb = KnowledgeBase.load(Path("games/shadow_fight_3/knowledge"))
    assert "jab_combo" in kb.moves
    assert "shadow_burst" in kb.moves
    assert kb.controls.joystick_center is not None
    assert "punch" in kb.controls.buttons
