"""Device Profile Manager: loads the manufacturer/device library from YAML.

No manufacturer, model, or device spec is hardcoded in Python --
everything comes from ``config/manufacturers.yaml`` (see
:class:`~ugaf.emulator.types.DeviceProfile`). Adding a new supported
device is a YAML edit, never a code change.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ugaf.emulator.types import DeviceProfile

__all__ = [
    "DeviceProfileManager",
]

_DEFAULT_PATH = Path("config/manufacturers.yaml")


class DeviceProfileManager:
    """Loads and queries the device profile library."""

    def __init__(self, path: Path | str | None = None) -> None:
        """Load device profiles from *path* (defaults to ``config/manufacturers.yaml``)."""
        self._path = Path(path) if path is not None else _DEFAULT_PATH
        self._profiles: dict[str, dict[str, DeviceProfile]] = self._load(self._path)

    def reload(self) -> None:
        """Re-read the backing YAML file, picking up any manual edits."""
        self._profiles = self._load(self._path)

    def manufacturers(self) -> list[str]:
        """Return every supported manufacturer name, sorted."""
        return sorted(self._profiles)

    def devices(self, manufacturer: str) -> list[DeviceProfile]:
        """Return every device profile for *manufacturer*, sorted by model name."""
        devices = self._profiles.get(manufacturer, {})
        return sorted(devices.values(), key=lambda d: d.model)

    def get(self, manufacturer: str, device_name: str) -> DeviceProfile:
        """Return a single device profile.

        Raises:
            KeyError: If *manufacturer* or *device_name* is unknown.

        """
        try:
            return self._profiles[manufacturer][device_name]
        except KeyError as exc:
            raise KeyError(
                f"Unknown device profile: manufacturer={manufacturer!r} device={device_name!r}"
            ) from exc

    def all_profiles(self) -> list[DeviceProfile]:
        """Return every device profile across every manufacturer."""
        return [profile for devices in self._profiles.values() for profile in devices.values()]

    @staticmethod
    def _load(path: Path) -> dict[str, dict[str, DeviceProfile]]:
        """Parse ``manufacturers.yaml`` into ``{manufacturer: {device_name: DeviceProfile}}``."""
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        manufacturers = data.get("manufacturers") or {}
        result: dict[str, dict[str, DeviceProfile]] = {}
        for manufacturer, section in manufacturers.items():
            devices = (section or {}).get("devices") or {}
            result[manufacturer] = {
                device_name: DeviceProfile.from_dict(manufacturer, device_data)
                for device_name, device_data in devices.items()
            }
        return result
