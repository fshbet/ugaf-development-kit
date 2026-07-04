"""Performance Profile Manager: loads emulator resource presets from YAML.

Mirrors :class:`~ugaf.emulator.profiles.DeviceProfileManager` for
:class:`~ugaf.emulator.types.PerformanceProfile` — presets (and the
editable ``custom`` starting point) live in
``config/performance_profiles.yaml``, never hardcoded here.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import yaml

from ugaf.emulator.types import PerformanceProfile

__all__ = [
    "PerformanceProfileManager",
]

_DEFAULT_PATH = Path("config/performance_profiles.yaml")


class PerformanceProfileManager:
    """Loads and queries performance presets."""

    def __init__(self, path: Path | str | None = None) -> None:
        """Load performance profiles from *path*.

        Defaults to ``config/performance_profiles.yaml``.
        """
        self._path = Path(path) if path is not None else _DEFAULT_PATH
        self._profiles: dict[str, PerformanceProfile] = self._load(self._path)

    def reload(self) -> None:
        """Re-read the backing YAML file, picking up any manual edits."""
        self._profiles = self._load(self._path)

    def names(self) -> list[str]:
        """Return every preset name, sorted."""
        return sorted(self._profiles)

    def get(self, name: str) -> PerformanceProfile:
        """Return a single performance profile by name.

        Raises:
            KeyError: If *name* is unknown.

        """
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise KeyError(f"Unknown performance profile: {name!r}") from exc

    def custom(self, **overrides: object) -> PerformanceProfile:
        """Return the ``custom`` preset with *overrides* applied.

        Usage::

            manager.custom(ram_mb=6144, cpu_count=4)

        """
        base = self.get("custom")
        return dataclasses.replace(base, **overrides)  # type: ignore[arg-type]

    @staticmethod
    def _load(path: Path) -> dict[str, PerformanceProfile]:
        """Parse ``performance_profiles.yaml`` into ``{name: PerformanceProfile}``."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        profiles = data.get("profiles") or {}
        return {
            name: PerformanceProfile.from_dict(name, profile_data)
            for name, profile_data in profiles.items()
        }
