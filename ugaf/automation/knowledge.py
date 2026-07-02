"""Knowledge base: loads move and control definitions from a game's YAML files.

Games describe *what* moves exist and *where* controls are on screen
as data (``knowledge/moves.yaml``, ``knowledge/buttons.yaml``) rather
than Python, so editing a move sequence or recalibrating a button
position never requires a code change. See
``games/shadow_fight_3/knowledge/`` for a worked example.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "ControlLayout",
    "KnowledgeBase",
    "MoveDefinition",
]


@dataclass(frozen=True)
class MoveDefinition:
    """A named move: an ordered action-step sequence plus descriptive metadata.

    Each step in ``sequence`` is a single-key dict naming an
    :class:`~ugaf.automation.executor.Executor` verb, e.g.
    ``{"tap": "punch"}``, ``{"move": "right"}``,
    ``{"hold": {"button": "punch", "duration": 0.6}}``, or
    ``{"wait": 0.5}``.
    """

    name: str
    sequence: list[dict[str, Any]]
    cooldown: float = 0.0
    damage: float = 0.0
    shadow_cost: float = 0.0
    range: str = "melee"
    startup: float = 0.0
    recovery: float = 0.0
    priority: int = 0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlLayout:
    """Resolves named controls (buttons, an analog joystick) to pixel coordinates.

    All positions are stored as fractions of screen width/height
    (0.0-1.0) so one layout works across device resolutions without
    recalibration.
    """

    buttons: dict[str, tuple[float, float]]
    joystick_center: tuple[float, float] | None
    joystick_radius: float

    def button_point(self, name: str, screen_size: tuple[int, int]) -> tuple[int, int]:
        """Resolve a named button to absolute pixel coordinates.

        Raises:
            KeyError: If *name* is not a known button.

        """
        width, height = screen_size
        fx, fy = self.buttons[name]
        return round(fx * width), round(fy * height)

    def joystick_point(
        self, direction: tuple[float, float], screen_size: tuple[int, int]
    ) -> tuple[int, int]:
        """Resolve a unit-vector joystick direction to absolute pixel coordinates.

        Raises:
            KeyError: If this layout has no analog joystick defined.

        """
        if self.joystick_center is None:
            raise KeyError("No joystick defined in this control layout")
        width, height = screen_size
        cx, cy = self.joystick_center
        px, py = cx * width, cy * height
        radius = self.joystick_radius * width
        dx, dy = direction
        return round(px + dx * radius), round(py + dy * radius)


@dataclass
class KnowledgeBase:
    """A game's full knowledge: its moves and its control layout."""

    moves: dict[str, MoveDefinition]
    controls: ControlLayout

    @classmethod
    def load(cls, knowledge_dir: Path) -> KnowledgeBase:
        """Load ``moves.yaml`` and ``buttons.yaml`` from *knowledge_dir*."""
        return cls(
            moves=_load_moves(knowledge_dir / "moves.yaml"),
            controls=_load_controls(knowledge_dir / "buttons.yaml"),
        )


def _load_moves(path: Path) -> dict[str, MoveDefinition]:
    data = yaml.safe_load(path.read_text()) or {}
    moves: dict[str, MoveDefinition] = {}
    for name, spec in (data.get("moves") or {}).items():
        spec = spec or {}
        moves[name] = MoveDefinition(
            name=name,
            sequence=list(spec.get("sequence") or []),
            cooldown=float(spec.get("cooldown", 0.0)),
            damage=float(spec.get("damage", 0.0)),
            shadow_cost=float(spec.get("shadow_cost", 0.0)),
            range=str(spec.get("range", "melee")),
            startup=float(spec.get("startup", 0.0)),
            recovery=float(spec.get("recovery", 0.0)),
            priority=int(spec.get("priority", 0)),
            tags=tuple(spec.get("tags") or ()),
        )
    return moves


def _load_controls(path: Path) -> ControlLayout:
    data = yaml.safe_load(path.read_text()) or {}
    controls = data.get("controls") or {}
    buttons: dict[str, tuple[float, float]] = {}
    joystick_center: tuple[float, float] | None = None
    joystick_radius = 0.0
    for name, spec in controls.items():
        spec = spec or {}
        if spec.get("type") == "analog":
            center = spec.get("center") or {}
            joystick_center = (float(center.get("x", 0.0)), float(center.get("y", 0.0)))
            joystick_radius = float(spec.get("radius", 0.0))
        else:
            position = spec.get("position") or {}
            buttons[name] = (float(position.get("x", 0.0)), float(position.get("y", 0.0)))
    return ControlLayout(
        buttons=buttons, joystick_center=joystick_center, joystick_radius=joystick_radius
    )
