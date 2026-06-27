"""Capability model for UGAF game plugins."""

from __future__ import annotations

from enum import Enum

__all__ = [
    "Capability",
]


class Capability(Enum):
    """Capabilities a game plugin can declare.

    Attributes:
        INPUT: Direct input simulation (mouse, keyboard, touch).
        VISION: Screen capture and image recognition.
        OCR: Optical character recognition.
        SCREENSHOT: Screen capture capability.
        MULTI_DEVICE: Support for multiple device targets.
        ADB: Android Debug Bridge connectivity.
        WINDOWS: Windows-native input simulation.

    """

    INPUT = "input"
    VISION = "vision"
    OCR = "ocr"
    SCREENSHOT = "screenshot"
    MULTI_DEVICE = "multi_device"
    ADB = "adb"
    WINDOWS = "windows"
