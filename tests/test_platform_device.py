"""Tests for the Device abstraction contract."""

from __future__ import annotations

from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus


class _StaticDeviceProvider(DeviceProvider):
    def __init__(self, devices: list[DeviceInfo]) -> None:
        self._devices = devices

    def list_devices(self) -> list[DeviceInfo]:
        return list(self._devices)

    def get_device(self, device_id: str) -> DeviceInfo | None:
        for device in self._devices:
            if device.id == device_id:
                return device
        return None


def test_device_info_is_immutable() -> None:
    info = DeviceInfo(
        id="serial-1",
        name="Pixel 7",
        status=DeviceStatus.ONLINE,
        platform="android",
        transport="adb",
    )
    assert info.extra == {}
    try:
        info.id = "changed"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("DeviceInfo should be frozen")


def test_device_provider_list_and_get() -> None:
    device = DeviceInfo(
        id="serial-1",
        name="Pixel 7",
        status=DeviceStatus.ONLINE,
        platform="android",
        transport="adb",
        extra={"api_level": "34"},
    )
    provider = _StaticDeviceProvider([device])

    assert provider.list_devices() == [device]
    assert provider.get_device("serial-1") == device
    assert provider.get_device("missing") is None


def test_device_status_values() -> None:
    assert DeviceStatus.ONLINE.value == "online"
    assert DeviceStatus.OFFLINE.value == "offline"
    assert DeviceStatus.UNAUTHORIZED.value == "unauthorized"
    assert DeviceStatus.UNKNOWN.value == "unknown"
