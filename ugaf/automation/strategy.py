"""Strategy engine: picks which move(s) to run each cycle from a data-driven strategy file.

Strategies are ordered condition -> move-sequence rule lists (see
``games/shadow_fight_3/strategies/`` for worked examples), so a
designer changes a game's behaviour by editing YAML, never by
touching plugin code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

__all__ = [
    "Strategy",
    "StrategyEngine",
]


@dataclass(frozen=True)
class _Rule:
    when: dict[str, Any] | str
    do: list[str]


@dataclass
class Strategy:
    """A named, ordered set of condition -> move-sequence rules."""

    name: str
    cycle_interval: float
    rules: list[_Rule]

    @classmethod
    def load(cls, path: Path) -> Strategy:
        """Load a strategy from a YAML file."""
        data = yaml.safe_load(path.read_text()) or {}
        rules = []
        for rule in data.get("rules") or []:
            do = rule["do"]
            rules.append(
                _Rule(
                    when=rule.get("when", "always"),
                    do=[do] if isinstance(do, str) else list(do),
                )
            )
        return cls(
            name=str(data.get("name", path.stem)),
            cycle_interval=float(data.get("cycle_interval", 1.0)),
            rules=rules,
        )


class StrategyEngine:
    """Evaluates a :class:`Strategy`'s rules against the current cycle state.

    Rules are evaluated top-down; the first matching rule's moves are
    returned. Supported conditions today: ``"always"`` and
    ``{"cycle_mod": N}`` (true when ``state["cycle"] % N == 0``) — the
    small vocabulary the bundled strategies need to reproduce a
    rotating combat pattern. Extend :func:`_condition_matches` as new
    condition types (e.g. vision-derived facts like enemy distance or
    health percentage) become available; strategy YAML files can
    reference them without any other code changing.
    """

    def __init__(self, strategy: Strategy) -> None:
        """Wrap a loaded :class:`Strategy` for per-cycle evaluation."""
        self._strategy = strategy

    @property
    def name(self) -> str:
        """Return the strategy's name."""
        return self._strategy.name

    @property
    def cycle_interval(self) -> float:
        """Return the delay (seconds) a caller should wait between cycles."""
        return self._strategy.cycle_interval

    def select(self, state: dict[str, Any]) -> list[str]:
        """Return the ordered move names to execute for the current *state*."""
        for rule in self._strategy.rules:
            if _condition_matches(rule.when, state):
                return rule.do
        return []


def _condition_matches(condition: dict[str, Any] | str, state: dict[str, Any]) -> bool:
    if condition == "always":
        return True
    if isinstance(condition, dict) and "cycle_mod" in condition:
        n = int(condition["cycle_mod"])
        cycle = int(state.get("cycle", 0))
        return n > 0 and cycle % n == 0
    return False
