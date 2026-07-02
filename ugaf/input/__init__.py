"""Input automation engine for the Universal Game Automation Framework."""

from ugaf.input.adb import AdbInputProvider
from ugaf.input.exceptions import (
    ConnectionFailedError,
    CoordinateOutOfBoundsError,
    DeviceNotFoundError,
    InputError,
    ProviderNotAvailableError,
)
from ugaf.input.manager import InputManager
from ugaf.input.mock import MockInputProvider
from ugaf.input.provider import InputProvider
from ugaf.input.registry import InputProviderRegistry, registry
from ugaf.input.types import Button, Key, Point
from ugaf.input.windows import WindowsInputProvider

# Register built-in providers during application bootstrap.
registry.register("windows", WindowsInputProvider)
registry.register("adb", AdbInputProvider)
registry.register("mock", MockInputProvider)

__all__ = [
    "AdbInputProvider",
    "Button",
    "ConnectionFailedError",
    "CoordinateOutOfBoundsError",
    "DeviceNotFoundError",
    "InputError",
    "InputManager",
    "InputProvider",
    "InputProviderRegistry",
    "Key",
    "MockInputProvider",
    "Point",
    "ProviderNotAvailableError",
    "WindowsInputProvider",
    "registry",
]
