"""Data-driven automation stack: Knowledge -> Strategy -> Executor.

Reusable across any plugin that wants game logic to live in YAML
rather than Python. See ``games/shadow_fight_3`` for a worked example
and its ``README.md`` for the file layout.
"""

from __future__ import annotations

from ugaf.automation.executor import Executor
from ugaf.automation.knowledge import ControlLayout, KnowledgeBase, MoveDefinition
from ugaf.automation.strategy import Strategy, StrategyEngine

__all__ = [
    "ControlLayout",
    "Executor",
    "KnowledgeBase",
    "MoveDefinition",
    "Strategy",
    "StrategyEngine",
]
