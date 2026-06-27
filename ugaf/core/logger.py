"""Structured logging with rotation and configurable levels."""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from ugaf.core.config import Config


@dataclass
class LoggerConfig:
    """Configuration for the structured logger.

    Attributes:
        level: Minimum logging level (e.g. ``"DEBUG"``, ``"INFO"``).
        file_path: Optional path to a log file. If set, logs are written
            to this file with rotation.
        max_bytes: Maximum size in bytes of a single log file before
            rotation (default 10 MB).
        backup_count: Number of rotated log files to keep (default 5).
        json_format: If ``True``, output JSON-formatted logs for
            production environments.

    """

    level: str = "INFO"
    file_path: str | None = None
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    json_format: bool = False


def _get_level_number(level: str) -> int:
    """Convert a level string to a logging constant.

    Args:
        level: Log level name (case-insensitive).

    Returns:
        Corresponding ``logging`` level constant.

    """
    normalized = level.upper()
    numeric = getattr(logging, normalized, None)
    if not isinstance(numeric, int):
        raise ValueError(f"Unknown log level: {level!r}")
    return numeric


class Logger:
    """Structured logger wrapping *structlog*.

    Usage::

        logger = Logger(config)
        logger.info("app.started", app="UGAF", version="1.0")
        logger.error("db.connection_failed", host=host, exc_info=True)
    """

    def __init__(self, log_config: LoggerConfig | Config | None = None) -> None:
        """Initialise the structured logger.

        Args:
            log_config: A ``LoggerConfig`` instance or a ``Config``
                instance from which logger settings are read under the
                ``logging`` key.

        """
        if isinstance(log_config, Config):
            resolved = LoggerConfig(
                level=log_config.get("logging.level", "INFO"),
                file_path=log_config.get("logging.file_path"),
                max_bytes=log_config.get("logging.max_bytes", 10 * 1024 * 1024),
                backup_count=log_config.get("logging.backup_count", 5),
                json_format=log_config.get("logging.json_format", False),
            )
        elif log_config is not None:
            resolved = log_config
        else:
            resolved = LoggerConfig()

        self._config = resolved
        level_number = _get_level_number(resolved.level)

        # Configure standard logging
        root_logger = logging.getLogger()
        root_logger.setLevel(level_number)

        # Remove default handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level_number)
        root_logger.addHandler(console_handler)

        # File handler with rotation
        if resolved.file_path:
            log_path = Path(resolved.file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                str(log_path),
                maxBytes=resolved.max_bytes,
                backupCount=resolved.backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(level_number)
            root_logger.addHandler(file_handler)

        # Configure structlog
        processors: list[Any] = [
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
        ]

        if resolved.json_format:
            processors.append(structlog.processors.JSONRenderer())
        else:
            processors.append(
                structlog.dev.ConsoleRenderer(
                    colors=sys.stdout.isatty(),
                    sort_keys=False,
                )
            )

        structlog.configure(
            processors=processors,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        self._logger = structlog.get_logger()

    @property
    def level(self) -> str:
        """Return the current log level as a string."""
        return self._config.level

    def debug(self, event: str, **kwargs: Any) -> None:
        """Log a debug message.

        Args:
            event: Structured event name (e.g. ``"db.query"``).
            **kwargs: Additional structured context.

        """
        self._logger.debug(event, **kwargs)

    def info(self, event: str, **kwargs: Any) -> None:
        """Log an informational message.

        Args:
            event: Structured event name.
            **kwargs: Additional structured context.

        """
        self._logger.info(event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        """Log a warning.

        Args:
            event: Structured event name.
            **kwargs: Additional structured context.

        """
        self._logger.warning(event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        """Log an error.

        Args:
            event: Structured event name.
            **kwargs: Additional structured context.

        """
        self._logger.error(event, **kwargs)

    def critical(self, event: str, **kwargs: Any) -> None:
        """Log a critical message.

        Args:
            event: Structured event name.
            **kwargs: Additional structured context.

        """
        self._logger.critical(event, **kwargs)


_logger_instance: Logger | None = None


def get_logger() -> Logger:
    """Return the global logger instance.

    Returns:
        The global ``Logger`` instance. If not yet configured,
        creates one with default settings.

    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger()
    return _logger_instance


def configure_logger(log_config: LoggerConfig | Config) -> Logger:
    """Configure and set the global logger instance.

    Args:
        log_config: Logger configuration.

    Returns:
        The configured ``Logger`` instance.

    """
    global _logger_instance
    _logger_instance = Logger(log_config)
    return _logger_instance
