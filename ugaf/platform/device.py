"""Device enumeration abstraction.

This module defines the narrow seam a transport (ADB, a future
wireless/USB Windows transport, etc.) must implement so the Device
Manager (Milestone 3) can enumerate and describe devices uniformly.

Connection lifecycle, reconnection, heartbeat, and health monitoring
intentionally do NOT live here — that orchestration spans multiple
:class:`DeviceProvider` transports at once and belongs one layer up,
in the Device Manager itself. This module only answers "what devices
exist and what do we know about them right now".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "DeviceInfo",
    "DeviceProvider",
    "DeviceStatus",
]


class DeviceStatus(Enum):
    """Connection status of a discovered device.

    Attributes:
        ONLINE: Device is present and ready to accept commands.
        OFFLINE: Device was previously known but is not currently
            reachable.
        UNAUTHORIZED: Device is physically present but has not
            authorized this host (e.g. ADB USB debugging prompt not
            yet accepted).
        UNKNOWN: Status could not be determined.

    """

    ONLINE = "online"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class DeviceInfo:
    """Immutable snapshot of a single device as reported by a transport.

    Attributes:
        id: Transport-specific unique identifier (e.g. an ADB serial).
        name: Human-readable device name/model, if known.
        status: Current connection status.
        platform: Target OS running on the device (e.g.
            ``"android"``).
        transport: Identifier of the transport that reported this
            device (e.g. ``"adb"``).
        extra: Transport-specific metadata not covered by the fields
            above (e.g. Android API level, USB vs. wireless).

    """

    id: str
    name: str
    status: DeviceStatus
    platform: str
    transport: str
    extra: dict[str, str] = field(default_factory=dict)


class DeviceProvider(ABC):
    """Abstract interface for a single transport's device enumeration.

    Concrete adapters (e.g. an ADB-backed provider) are introduced in
    Milestone 4 (Android Transport); this module only defines the
    contract the Device Manager depends on.
    """

    @abstractmethod
    def list_devices(self) -> list[DeviceInfo]:
        """Return every device currently visible to this transport.

        Returns:
            A list of :class:`DeviceInfo`, possibly empty.

        """

    @abstractmethod
    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Return a single device by its transport-specific identifier.

        Args:
            device_id: The device identifier to look up.

        Returns:
            The matching :class:`DeviceInfo`, or ``None`` if not
            currently visible to this transport.

        """
