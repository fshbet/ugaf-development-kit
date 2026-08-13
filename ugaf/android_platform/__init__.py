"""Android Platform Manager: the single component that understands Android SDK tooling.

Per ADR-021, ``sdkmanager``/``avdmanager``/``emulator.exe``/``adb.exe``
are implementation details the rest of UGAF should never need to know
about. :class:`~ugaf.android_platform.manager.AndroidPlatformManager` is
the one component that does — everything else (the webapp, future
callers) talks to it in Android domain terms (Virtual Devices, Physical
Devices, Platform Health), not SDK-tool terms.
"""

from __future__ import annotations

from ugaf.android_platform.manager import AndroidPlatformManager, PlatformHealth

__all__ = [
    "AndroidPlatformManager",
    "PlatformHealth",
]
