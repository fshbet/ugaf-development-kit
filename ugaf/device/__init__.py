"""Device Manager subsystem for the UGAF framework.

The Core Engine and game plugins never talk to ADB (or any future
transport) directly — everything flows through
:class:`ugaf.device.manager.DeviceManager`, which orchestrates one or
more :class:`ugaf.platform.device.DeviceProvider` transports.

See ``ANDROID_TRANSPORT_STRATEGY.md`` for the research and rationale
behind starting with ADB as the first transport, and
``PLATFORM_ABSTRACTION.md`` for how ``DeviceProvider`` fits into the
broader Platform Abstraction Layer.
"""

from __future__ import annotations

from ugaf.device.adb_provider import AdbDeviceProvider
from ugaf.device.exceptions import DeviceCommandError, DeviceManagerError
from ugaf.device.manager import DeviceManager

__all__ = [
    "AdbDeviceProvider",
    "DeviceCommandError",
    "DeviceManager",
    "DeviceManagerError",
]
