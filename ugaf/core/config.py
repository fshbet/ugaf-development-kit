"""Configuration system with YAML loading and environment variable overrides."""

from __future__ import annotations

from os import environ
from pathlib import Path
from typing import Any

import yaml

from ugaf.core.exceptions import ConfigError

__all__ = [
    "Config",
    "ConfigError",
]


def _env_key(key: str) -> str:
    """Convert a dotted config key to an environment variable name.

    Args:
        key: Dotted configuration key (e.g. "logging.level").

    Returns:
        Upper-case environment variable name with UGAF_ prefix.

    """
    return f"UGAF_{key.upper().replace('.', '_')}"


def _merge_env_overrides(data: dict[str, Any], prefix: str = "") -> None:
    """Recursively merge environment variable overrides into the config dict.

    For each leaf value, check if an environment variable exists at the
    current key path and replace the value if it does.

    Args:
        data: Configuration dictionary to mutate in-place.
        prefix: Accumulated dotted key prefix for recursion.

    """
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        env_name = _env_key(full_key)
        env_value = environ.get(env_name)
        if env_value is not None:
            data[key] = _coerce(env_value)
        elif isinstance(value, dict):
            _merge_env_overrides(value, full_key)


def _coerce(value: str) -> bool | int | float | str:
    """Coerce a string to its most specific type.

    Args:
        value: String value to coerce.

    Returns:
        Coerced value as bool, int, float, or str.

    """
    lower = value.lower()
    if lower in ("true", "yes", "1"):
        return True
    if lower in ("false", "no", "0"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge two dictionaries.

    Args:
        base: Base dictionary.
        override: Override dictionary whose values take precedence.

    Returns:
        New merged dictionary.

    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    """Application configuration loaded from YAML with env-var overrides.

    Usage::

        config = Config(config_path / "default.yaml")
        config.get("logging.level")
        config.get("nonexistent", fallback="info")
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        """Initialise Config and optionally load from a YAML file.

        Args:
            config_path: Path to a YAML configuration file. If ``None``,
                the config starts empty.

        """
        self._data: dict[str, Any] = {}
        if config_path is not None:
            self.load(Path(config_path))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Build a Config directly from an in-memory dict, without a YAML file.

        Useful for a caller that needs a small, local config override
        independent of the shared application config (e.g. forcing a
        specific input provider for one connection) without writing a
        temporary file.

        Args:
            data: Configuration values, in the same nested-dict shape
                a loaded YAML file would produce.

        Returns:
            A new ``Config`` with *data* as its contents (still subject
            to environment variable overrides, exactly like a loaded
            file).

        """
        config = cls()
        config._data = _deep_merge(config._data, data)
        _merge_env_overrides(config._data)
        return config

    def load(self, config_path: Path) -> None:
        """Load configuration from a YAML file.

        If ``self._data`` already contains values (e.g. from a previous
        call), the loaded file is deep-merged on top.

        Args:
            config_path: Path to a YAML configuration file.

        Raises:
            ConfigError: If the file cannot be read or parsed.

        """
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                raw: Any = yaml.safe_load(fh)
            if raw is not None and not isinstance(raw, dict):
                raise ConfigError(
                    f"Config file {config_path} must contain a YAML mapping "
                    f"(got {type(raw).__name__})"
                )
            parsed: dict[str, Any] = raw if raw is not None else {}
        except (OSError, yaml.YAMLError) as exc:
            raise ConfigError(f"Cannot load config file {config_path}: {exc}") from exc

        self._data = _deep_merge(self._data, parsed)
        _merge_env_overrides(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a configuration value by dotted key.

        Args:
            key: Dotted path to the configuration value.
            default: Value returned when the key is not found.

        Returns:
            The configuration value or *default*.

        """
        parts = key.split(".")
        current: Any = self._data
        for part in parts:
            if not isinstance(current, dict):
                return default
            current = current.get(part)
            if current is None:
                return default
        return current

    def __repr__(self) -> str:
        """Return a string representation of the configuration."""
        return f"Config({self._data!r})"
