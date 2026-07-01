"""Tests for the UGAF command-line interface."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ugaf.core.cli import build_parser, run_cli


def _write_config(path: Path, data: dict) -> Path:  # type: ignore[type-arg]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data))
    return path


def test_build_parser_defines_all_subcommands() -> None:
    parser = build_parser()
    args = parser.parse_args(["start"])
    assert args.command == "start"


def test_run_cli_no_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_cli([])
    assert exit_code == 1
    captured = capsys.readouterr()
    assert "usage" in captured.out.lower()


def test_run_cli_version_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_cli(["version"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "UGAF version" in captured.out


def test_run_cli_stop_command(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = run_cli(["stop"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "SIGINT" in captured.out


def test_build_parser_rejects_unknown_command() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["bogus"])


def test_run_cli_health_command_reports_healthy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path / "config.yaml", {"logging": {"level": "INFO"}})
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    exit_code = run_cli(["--config", str(config_path), "--games-dir", str(games_dir), "health"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "healthy" in captured.out
    assert "plugin_manager" in captured.out


def test_run_cli_plugins_command_discovers_example_game(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path / "config.yaml", {"logging": {"level": "INFO"}})
    games_dir = Path("games")

    exit_code = run_cli(["--config", str(config_path), "--games-dir", str(games_dir), "plugins"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Example Game" in captured.out
    assert "example_game" in captured.out


def test_run_cli_plugins_command_no_plugins(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = _write_config(tmp_path / "config.yaml", {"logging": {"level": "INFO"}})
    games_dir = tmp_path / "games"
    games_dir.mkdir()

    exit_code = run_cli(["--config", str(config_path), "--games-dir", str(games_dir), "plugins"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No plugins discovered" in captured.out
