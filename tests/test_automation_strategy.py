"""Tests for ugaf.automation.strategy: Strategy/StrategyEngine."""

from __future__ import annotations

from pathlib import Path

from ugaf.automation.strategy import Strategy, StrategyEngine


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_loads_strategy_name_and_interval(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.yaml",
        """
name: my_strategy
cycle_interval: 2.5
rules:
  - when: always
    do: advance
""",
    )
    strategy = Strategy.load(path)
    assert strategy.name == "my_strategy"
    assert strategy.cycle_interval == 2.5


def test_first_matching_rule_wins_top_down(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.yaml",
        """
name: rotation
cycle_interval: 1.0
rules:
  - when: { cycle_mod: 3 }
    do: [special]
  - when: always
    do: [basic]
""",
    )
    engine = StrategyEngine(Strategy.load(path))
    assert engine.select({"cycle": 3}) == ["special"]
    assert engine.select({"cycle": 6}) == ["special"]
    assert engine.select({"cycle": 1}) == ["basic"]
    assert engine.select({"cycle": 2}) == ["basic"]


def test_do_accepts_single_string_or_list(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.yaml",
        """
name: mixed
cycle_interval: 1.0
rules:
  - when: always
    do: solo_move
""",
    )
    engine = StrategyEngine(Strategy.load(path))
    assert engine.select({"cycle": 1}) == ["solo_move"]


def test_no_matching_rule_returns_empty_list(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "s.yaml",
        """
name: no_default
cycle_interval: 1.0
rules:
  - when: { cycle_mod: 5 }
    do: [special]
""",
    )
    engine = StrategyEngine(Strategy.load(path))
    assert engine.select({"cycle": 1}) == []


def test_bundled_shadow_fight_3_strategies_load_and_select() -> None:
    for name in ("balanced", "aggressive", "defensive"):
        strategy = Strategy.load(Path(f"games/shadow_fight_3/strategies/{name}.yaml"))
        engine = StrategyEngine(strategy)
        assert engine.cycle_interval > 0
        # Every strategy must produce moves for at least one cycle (the
        # "always" fallback rule, if nothing else).
        assert any(engine.select({"cycle": c}) for c in range(1, 10))
