"""Tests for the Config module."""

from __future__ import annotations

from pathlib import Path

import pytest

from ugaf.core.config import Config, ConfigError


def test_config_loads_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("logging:\n  level: DEBUG\n  json_format: false\n")
    cfg = Config(config_file)
    assert cfg.get("logging.level") == "DEBUG"
    assert cfg.get("logging.json_format") is False


def test_config_default_when_missing_key(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("logging:\n  level: INFO\n")
    cfg = Config(config_file)
    assert cfg.get("logging.level") == "INFO"
    assert cfg.get("nonexistent.key", "fallback") == "fallback"


def test_config_empty_file(tmp_path: Path) -> None:
    config_file = tmp_path / "empty.yaml"
    config_file.write_text("")
    cfg = Config(config_file)
    assert cfg.get("anything") is None


def test_config_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Config(tmp_path / "does_not_exist.yaml")


def test_config_raises_on_invalid_yaml(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.yaml"
    config_file.write_text(": invalid yaml :\n")
    with pytest.raises(ConfigError):
        Config(config_file)


def test_config_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("logging:\n  level: INFO\n")

    monkeypatch.setenv("UGAF_LOGGING_LEVEL", "DEBUG")
    cfg = Config(config_file)
    assert cfg.get("logging.level") == "DEBUG"


def test_config_env_override_nested(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("database:\n  host: localhost\n  port: 5432\n")

    monkeypatch.setenv("UGAF_DATABASE_HOST", "db.example.com")
    cfg = Config(config_file)
    assert cfg.get("database.host") == "db.example.com"
    assert cfg.get("database.port") == 5432


def test_config_env_coerce_bool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("feature:\n  enabled: false\n")

    monkeypatch.setenv("UGAF_FEATURE_ENABLED", "true")
    cfg = Config(config_file)
    assert cfg.get("feature.enabled") is True


def test_config_env_coerce_int(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("server:\n  port: 8080\n")

    monkeypatch.setenv("UGAF_SERVER_PORT", "3000")
    cfg = Config(config_file)
    assert cfg.get("server.port") == 3000
    assert isinstance(cfg.get("server.port"), int)


def test_config_env_coerce_float(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("rate:\n  limit: 0.5\n")

    monkeypatch.setenv("UGAF_RATE_LIMIT", "1.5")
    cfg = Config(config_file)
    assert cfg.get("rate.limit") == 1.5
    assert isinstance(cfg.get("rate.limit"), float)


def test_config_merge_multiple_files(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    base.write_text("a: 1\nb: 2\n")

    override = tmp_path / "override.yaml"
    override.write_text("b: 3\nc: 4\n")

    cfg = Config(base)
    cfg.load(override)
    assert cfg.get("a") == 1
    assert cfg.get("b") == 3
    assert cfg.get("c") == 4


def test_config_empty_on_no_path() -> None:
    cfg = Config()
    assert cfg.get("anything") is None


def test_config_repr(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("key: value\n")
    cfg = Config(config_file)
    assert repr(cfg).startswith("Config(")


def test_config_raises_on_yaml_list(tmp_path: Path) -> None:
    config_file = tmp_path / "list.yaml"
    config_file.write_text("- item1\n- item2\n")
    with pytest.raises(ConfigError, match="YAML mapping"):
        Config(config_file)


def test_config_raises_on_yaml_scalar(tmp_path: Path) -> None:
    config_file = tmp_path / "scalar.yaml"
    config_file.write_text("just a string\n")
    with pytest.raises(ConfigError, match="YAML mapping"):
        Config(config_file)
