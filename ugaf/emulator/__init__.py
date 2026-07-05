"""Emulator Manager subsystem: choose and manage Android Emulator instances.

Extends UGAF's device layer so a user can automate either a physical
device (ADB, via :class:`~ugaf.device.manager.DeviceManager`, as
before) or an Android Emulator instance managed here — both become
ordinary ``adb`` serials once running, so every other layer (input,
vision, ``ApplicationManager``, ``PluginManager``) needs no emulator-
specific code at all. See ``ARCHITECTURE_DECISIONS.md`` for the ADR.
"""

from ugaf.emulator.android_versions import AndroidVersionManager
from ugaf.emulator.dependencies import DependencyReport, DependencyStatus, EnvironmentChecker
from ugaf.emulator.exceptions import (
    AvdAlreadyExistsError,
    AvdNotFoundError,
    EmulatorBootTimeoutError,
    EmulatorCommandError,
    EmulatorManagerError,
    SdkNotFoundError,
    SystemImageNotAvailableError,
)
from ugaf.emulator.hardware import HardwareDetector, HardwareInfo
from ugaf.emulator.manager import EmulatorManager
from ugaf.emulator.performance import PerformanceProfileManager
from ugaf.emulator.profiles import DeviceProfileManager
from ugaf.emulator.provider import EmulatorProvider
from ugaf.emulator.provider import emulator_registry as emulator_registry
from ugaf.emulator.providers.android_studio import AndroidStudioProvider
from ugaf.emulator.sdk_locator import AndroidSdkLocator, AndroidSdkPaths
from ugaf.emulator.studio_locator import AndroidStudioLocator
from ugaf.emulator.types import (
    AvdInfo,
    DeviceProfile,
    EmulatorInstanceHandle,
    PerformanceProfile,
    SystemImageInfo,
)

# Register built-in providers during application bootstrap. Registration
# only stores the class + constructs it lazily -- importing this module
# never shells out to any SDK tool.
emulator_registry.register("android_studio", AndroidStudioProvider)

__all__ = [
    "AndroidSdkLocator",
    "AndroidSdkPaths",
    "AndroidStudioLocator",
    "AndroidStudioProvider",
    "AndroidVersionManager",
    "AvdAlreadyExistsError",
    "AvdInfo",
    "AvdNotFoundError",
    "DependencyReport",
    "DependencyStatus",
    "DeviceProfile",
    "DeviceProfileManager",
    "EmulatorBootTimeoutError",
    "EmulatorCommandError",
    "EmulatorInstanceHandle",
    "EmulatorManager",
    "EmulatorManagerError",
    "EmulatorProvider",
    "EnvironmentChecker",
    "HardwareDetector",
    "HardwareInfo",
    "PerformanceProfile",
    "PerformanceProfileManager",
    "SdkNotFoundError",
    "SystemImageInfo",
    "SystemImageNotAvailableError",
    "emulator_registry",
]
