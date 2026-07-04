"""Tests for ugaf.emulator's DeviceProfileManager and PerformanceProfileManager.

Runs against the real ``config/manufacturers.yaml``/``config/performance_profiles.yaml``
shipped with the project -- these are reference data, not mocked
fixtures, so a typo or structural break in the real config surfaces
here rather than only at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ugaf.emulator.performance import PerformanceProfileManager
from ugaf.emulator.profiles import DeviceProfileManager

_EXPECTED_MANUFACTURERS = {
    "Google",
    "Samsung",
    "OnePlus",
    "Nothing",
    "Xiaomi",
    "OPPO",
    "vivo",
    "Motorola",
    "Sony",
    "ASUS",
    "HONOR",
}


def test_real_manufacturers_config_has_every_required_manufacturer() -> None:
    manager = DeviceProfileManager()
    assert set(manager.manufacturers()) == _EXPECTED_MANUFACTURERS


def test_real_manufacturers_config_devices_have_required_fields() -> None:
    manager = DeviceProfileManager()
    for profile in manager.all_profiles():
        assert profile.model
        assert profile.api_level > 0
        assert len(profile.resolution) == 2
        assert profile.ram_mb > 0
        assert profile.cpu_count > 0
        assert profile.storage_mb > 0
        assert profile.abi


def test_samsung_devices_include_galaxy_s25_ultra() -> None:
    manager = DeviceProfileManager()
    models = {d.model for d in manager.devices("Samsung")}
    assert "Galaxy S25 Ultra" in models


def test_get_unknown_manufacturer_raises_keyerror() -> None:
    manager = DeviceProfileManager()
    with pytest.raises(KeyError):
        manager.get("NoSuchBrand", "no_such_device")


def test_custom_profile_path(tmp_path: Path) -> None:
    path = tmp_path / "manufacturers.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "manufacturers": {
                    "Acme": {
                        "devices": {
                            "acme_1": {
                                "brand": "Acme",
                                "model": "Acme One",
                                "device_name": "acme_1",
                                "hardware_name": "pixel_6",
                                "android_version": "Android 15",
                                "api_level": 35,
                                "resolution": [1080, 2400],
                                "dpi": 420,
                                "ram_mb": 4096,
                                "cpu_count": 4,
                                "storage_mb": 8192,
                                "abi": "x86_64",
                            }
                        }
                    }
                }
            }
        )
    )
    manager = DeviceProfileManager(path)
    assert manager.manufacturers() == ["Acme"]
    profile = manager.get("Acme", "acme_1")
    assert profile.model == "Acme One"
    assert profile.play_store is True  # default


def test_reload_picks_up_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "manufacturers.yaml"
    path.write_text(yaml.safe_dump({"manufacturers": {}}))
    manager = DeviceProfileManager(path)
    assert manager.manufacturers() == []

    path.write_text(
        yaml.safe_dump(
            {
                "manufacturers": {
                    "Acme": {
                        "devices": {
                            "acme_1": {
                                "model": "Acme One",
                                "device_name": "acme_1",
                                "hardware_name": "pixel_6",
                                "android_version": "Android 15",
                                "api_level": 35,
                                "resolution": [1080, 2400],
                                "dpi": 420,
                                "ram_mb": 4096,
                                "cpu_count": 4,
                                "storage_mb": 8192,
                                "abi": "x86_64",
                            }
                        }
                    }
                }
            }
        )
    )
    manager.reload()
    assert manager.manufacturers() == ["Acme"]


_EXPECTED_PRESETS = {"low_end", "mid_range", "flagship", "gaming", "custom"}


def test_real_performance_profiles_config_has_every_preset() -> None:
    manager = PerformanceProfileManager()
    assert set(manager.names()) == _EXPECTED_PRESETS


def test_gaming_preset_is_the_highest_spec() -> None:
    manager = PerformanceProfileManager()
    gaming = manager.get("gaming")
    low_end = manager.get("low_end")
    assert gaming.cpu_count > low_end.cpu_count
    assert gaming.ram_mb > low_end.ram_mb


def test_get_unknown_preset_raises_keyerror() -> None:
    manager = PerformanceProfileManager()
    with pytest.raises(KeyError):
        manager.get("no_such_preset")


def test_custom_applies_overrides() -> None:
    manager = PerformanceProfileManager()
    custom = manager.custom(ram_mb=6144, cpu_count=4)
    assert custom.ram_mb == 6144
    assert custom.cpu_count == 4
    assert custom.name == "custom"
