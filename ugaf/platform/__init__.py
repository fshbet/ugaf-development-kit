"""Platform Abstraction Layer for the UGAF framework.

Defines OS-independent interfaces for system-level concerns (display,
clipboard, file system, network, accessibility, notifications, process
management, and device enumeration) so that ``ugaf.core`` and game
plugins never depend on operating-system-specific APIs directly.

Two subsystems already had abstractions elsewhere before this package
existed and are intentionally not duplicated here:

- Input: :class:`ugaf.input.provider.InputProvider`
- Screenshot: :class:`ugaf.vision.screenshot.ScreenshotProvider`

See ``PLATFORM_ABSTRACTION.md`` for the full design and current
per-subsystem adapter coverage.
"""

from __future__ import annotations

from ugaf.platform.accessibility import AccessibilityNode, AccessibilityProvider
from ugaf.platform.clipboard import ClipboardProvider, WindowsClipboardProvider
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus
from ugaf.platform.display import DisplayInfo, DisplayProvider, WindowsDisplayProvider
from ugaf.platform.exceptions import (
    AdapterNotAvailableError,
    AdapterNotConnectedError,
    PlatformLayerError,
)
from ugaf.platform.filesystem import FileSystemProvider, LocalFileSystemProvider
from ugaf.platform.network import DefaultNetworkProvider, NetworkProvider
from ugaf.platform.notifications import NotificationProvider, WindowsNotificationProvider
from ugaf.platform.process import DefaultProcessManager, ProcessHandle, ProcessManager
from ugaf.platform.registry import AdapterRegistry

# Per-subsystem adapter registries. Concrete adapters are registered
# below as they become available; subsystems with no adapter yet
# (Device, Accessibility) still get a registry so callers have one
# consistent lookup pattern regardless of how many adapters currently
# exist for a given platform.
#
# Each interface passed below is intentionally abstract — the whole
# point of AdapterRegistry is to bind a registry to an ABC and accept
# only its concrete subclasses via register()/create(). mypy's
# type-abstract check assumes type[T] implies "will be instantiated
# directly", which doesn't apply here (AdapterRegistry never calls
# self._interface()), hence the ignores below.
clipboard_registry: AdapterRegistry[ClipboardProvider] = AdapterRegistry(
    ClipboardProvider  # type: ignore[type-abstract]
)
display_registry: AdapterRegistry[DisplayProvider] = AdapterRegistry(
    DisplayProvider  # type: ignore[type-abstract]
)
filesystem_registry: AdapterRegistry[FileSystemProvider] = AdapterRegistry(
    FileSystemProvider  # type: ignore[type-abstract]
)
network_registry: AdapterRegistry[NetworkProvider] = AdapterRegistry(
    NetworkProvider  # type: ignore[type-abstract]
)
notification_registry: AdapterRegistry[NotificationProvider] = AdapterRegistry(
    NotificationProvider  # type: ignore[type-abstract]
)
process_registry: AdapterRegistry[ProcessManager] = AdapterRegistry(
    ProcessManager  # type: ignore[type-abstract]
)
device_registry: AdapterRegistry[DeviceProvider] = AdapterRegistry(
    DeviceProvider  # type: ignore[type-abstract]
)
accessibility_registry: AdapterRegistry[AccessibilityProvider] = AdapterRegistry(
    AccessibilityProvider  # type: ignore[type-abstract]
)

clipboard_registry.register("windows", WindowsClipboardProvider)
display_registry.register("windows", WindowsDisplayProvider)
notification_registry.register("windows", WindowsNotificationProvider)
filesystem_registry.register("local", LocalFileSystemProvider)
network_registry.register("default", DefaultNetworkProvider)
process_registry.register("default", DefaultProcessManager)

__all__ = [
    "AccessibilityNode",
    "AccessibilityProvider",
    "AdapterNotAvailableError",
    "AdapterNotConnectedError",
    "AdapterRegistry",
    "ClipboardProvider",
    "DefaultNetworkProvider",
    "DefaultProcessManager",
    "DeviceInfo",
    "DeviceProvider",
    "DeviceStatus",
    "DisplayInfo",
    "DisplayProvider",
    "FileSystemProvider",
    "LocalFileSystemProvider",
    "NetworkProvider",
    "NotificationProvider",
    "PlatformLayerError",
    "ProcessHandle",
    "ProcessManager",
    "WindowsClipboardProvider",
    "WindowsDisplayProvider",
    "WindowsNotificationProvider",
    "accessibility_registry",
    "clipboard_registry",
    "device_registry",
    "display_registry",
    "filesystem_registry",
    "network_registry",
    "notification_registry",
    "process_registry",
]
