"""Tests for the Logger module."""

from __future__ import annotations

from pathlib import Path

from ugaf.core.config import Config
from ugaf.core.logger import Logger, LoggerConfig, configure_logger, get_logger


def test_logger_default_level() -> None:
    logger = Logger()
    assert logger.level == "INFO"


def test_logger_with_config_object(tmp_path: Path) -> None:
    log_file = tmp_path / "test.log"
    log_config = LoggerConfig(
        level="DEBUG",
        file_path=str(log_file),
        max_bytes=1024,
        backup_count=1,
        json_format=False,
    )
    logger = Logger(log_config)
    assert logger.level == "DEBUG"

    logger.info("test.event", key="value")
    content = log_file.read_text(encoding="utf-8")
    assert "test.event" in content


def test_logger_with_config_instance(tmp_path: Path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.write_text("logging:\n  level: WARNING\n  file_path: ''\n")
    cfg = Config(config_file)
    logger = Logger(cfg)
    assert logger.level == "WARNING"


def test_logger_configure_global(tmp_path: Path) -> None:
    log_config = LoggerConfig(level="ERROR")
    logger = configure_logger(log_config)
    assert logger.level == "ERROR"
    assert get_logger() is logger


def test_logger_log_methods(tmp_path: Path) -> None:
    log_file = tmp_path / "output.log"
    log_config = LoggerConfig(
        level="DEBUG",
        file_path=str(log_file),
    )
    logger = Logger(log_config)

    logger.debug("debug.msg")
    logger.info("info.msg", count=42)
    logger.warning("warn.msg")
    logger.error("error.msg")
    logger.critical("critical.msg")

    content = log_file.read_text(encoding="utf-8")
    assert "info.msg" in content
    assert "warn.msg" in content
    assert "error.msg" in content
    assert "critical.msg" in content


def test_logger_json_format(tmp_path: Path) -> None:
    log_file = tmp_path / "json.log"
    log_config = LoggerConfig(
        level="INFO",
        file_path=str(log_file),
        json_format=True,
    )
    logger = Logger(log_config)
    logger.info("structured.event", user="alice")

    content = log_file.read_text(encoding="utf-8")
    assert content.startswith("{")
    assert "structured.event" in content
    assert "alice" in content


def test_logger_file_rotation(tmp_path: Path) -> None:
    log_file = tmp_path / "rotate.log"
    log_config = LoggerConfig(
        level="INFO",
        file_path=str(log_file),
        max_bytes=100,
        backup_count=2,
    )
    logger = Logger(log_config)

    for i in range(100):
        logger.info("rotate.test", iteration=i)

    rotated = list(tmp_path.glob("rotate.log*"))
    assert len(rotated) > 1


def test_logger_invalid_level() -> None:
    import re

    import pytest

    with pytest.raises(ValueError, match=re.escape("Unknown log level: 'INVALID'")):
        Logger(LoggerConfig(level="INVALID"))
