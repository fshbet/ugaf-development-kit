"""Typed value objects for the Emulator Manager subsystem.

Everything a caller needs to describe "what device to emulate" or
"how fast should it run" is data, loaded from YAML (see
``config/manufacturers.yaml``/``config/performance_profiles.yaml``) —
mirroring how :class:`~ugaf.apps.types.AppDefinition` keeps an Android
application's identity out of Python. No device or performance preset
is hardcoded in the manager classes themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "AvdInfo",
    "DeviceProfile",
    "EmulatorInstanceHandle",
    "PerformanceProfile",
    "SystemImageInfo",
]


@dataclass(frozen=True)
class DeviceProfile:
    """A single Android device's identity and preferred hardware configuration.

    Attributes:
        manufacturer: Device manufacturer (e.g. ``"Samsung"``).
        brand: Marketing brand, when distinct from *manufacturer*
            (e.g. ``"Redmi"`` under manufacturer ``"Xiaomi"``).
        model: Marketing model name (e.g. ``"Galaxy S25 Ultra"``).
        device_name: Short identifier used as the profile key (e.g.
            ``"galaxy_s25_ultra"``).
        hardware_name: The ``avdmanager`` hardware/skin profile id to
            build the AVD from (e.g. ``"pixel_6_pro"``,
            ``"medium_phone"``) — the closest built-in device skin to
            this real device's screen/DPI.
        android_version: Marketing Android version name (e.g.
            ``"Android 15"``).
        api_level: Numeric Android API level (e.g. ``35``).
        resolution: Preferred ``(width, height)`` in pixels.
        dpi: Preferred screen density.
        ram_mb: Preferred RAM allocation in megabytes.
        cpu_count: Preferred virtual CPU core count.
        storage_mb: Preferred internal storage size in megabytes.
        abi: Preferred system image ABI (e.g. ``"x86_64"``,
            ``"arm64-v8a"``).
        gpu_mode: Preferred emulator GPU mode (``"auto"``, ``"host"``,
            ``"swiftshader_indirect"``, ...).
        play_store: Whether to prefer a Play Store-enabled system
            image for this profile.
        snapshot_support: Whether quick-boot snapshots should be
            enabled for AVDs created from this profile.

    """

    manufacturer: str
    brand: str
    model: str
    device_name: str
    hardware_name: str
    android_version: str
    api_level: int
    resolution: tuple[int, int]
    dpi: int
    ram_mb: int
    cpu_count: int
    storage_mb: int
    abi: str
    gpu_mode: str = "auto"
    play_store: bool = True
    snapshot_support: bool = True

    @classmethod
    def from_dict(cls, manufacturer: str, data: dict[str, object]) -> DeviceProfile:
        """Build a :class:`DeviceProfile` from one entry of ``manufacturers.yaml``."""
        resolution = data["resolution"]
        assert isinstance(resolution, (list, tuple))
        return cls(
            manufacturer=manufacturer,
            brand=str(data.get("brand", manufacturer)),
            model=str(data["model"]),
            device_name=str(data["device_name"]),
            hardware_name=str(data["hardware_name"]),
            android_version=str(data["android_version"]),
            api_level=int(data["api_level"]),  # type: ignore[call-overload]
            resolution=(int(resolution[0]), int(resolution[1])),
            dpi=int(data["dpi"]),  # type: ignore[call-overload]
            ram_mb=int(data["ram_mb"]),  # type: ignore[call-overload]
            cpu_count=int(data["cpu_count"]),  # type: ignore[call-overload]
            storage_mb=int(data["storage_mb"]),  # type: ignore[call-overload]
            abi=str(data.get("abi", "x86_64")),
            gpu_mode=str(data.get("gpu_mode", "auto")),
            play_store=bool(data.get("play_store", True)),
            snapshot_support=bool(data.get("snapshot_support", True)),
        )


@dataclass(frozen=True)
class PerformanceProfile:
    """A named preset (or user-customized set) of emulator resource limits.

    Attributes:
        name: Preset identifier (e.g. ``"gaming"``).
        cpu_count: Virtual CPU core count.
        ram_mb: RAM allocation in megabytes.
        heap_mb: Per-app Dalvik heap size in megabytes.
        storage_mb: Internal storage size in megabytes.
        resolution: Optional ``(width, height)`` override; ``None``
            keeps the device profile's own resolution.
        gpu_mode: Emulator GPU mode.
        network_speed: Emulated network speed (``"full"``, ``"lte"``,
            ``"edge"``, ...).
        snapshot_enabled: Whether quick-boot snapshots are enabled.

    """

    name: str
    cpu_count: int
    ram_mb: int
    heap_mb: int
    storage_mb: int
    resolution: tuple[int, int] | None = None
    gpu_mode: str = "auto"
    network_speed: str = "full"
    snapshot_enabled: bool = True

    @classmethod
    def from_dict(cls, name: str, data: dict[str, object]) -> PerformanceProfile:
        """Build a :class:`PerformanceProfile` from one entry of ``performance_profiles.yaml``."""
        raw_resolution = data.get("resolution")
        resolution: tuple[int, int] | None = None
        if raw_resolution:
            assert isinstance(raw_resolution, (list, tuple))
            resolution = (int(raw_resolution[0]), int(raw_resolution[1]))
        return cls(
            name=name,
            cpu_count=int(data["cpu_count"]),  # type: ignore[call-overload]
            ram_mb=int(data["ram_mb"]),  # type: ignore[call-overload]
            heap_mb=int(data.get("heap_mb", 256)),  # type: ignore[call-overload]
            storage_mb=int(data.get("storage_mb", 6144)),  # type: ignore[call-overload]
            resolution=resolution,
            gpu_mode=str(data.get("gpu_mode", "auto")),
            network_speed=str(data.get("network_speed", "full")),
            snapshot_enabled=bool(data.get("snapshot_enabled", True)),
        )


@dataclass(frozen=True)
class SystemImageInfo:
    """A single Android system image, installed or installable.

    Attributes:
        api_level: Numeric Android API level.
        version_name: Marketing version name (e.g. ``"Android 15"``),
            when known.
        tag: System image flavor (e.g. ``"google_apis_playstore"``,
            ``"google_apis"``, ``"default"``).
        abi: System image ABI (e.g. ``"x86_64"``).
        installed: Whether this image is already installed locally.
        package_path: The ``sdkmanager`` package path (e.g.
            ``"system-images;android-35;google_apis_playstore;x86_64"``).

    """

    api_level: int
    version_name: str | None
    tag: str
    abi: str
    installed: bool
    package_path: str


@dataclass(frozen=True)
class AvdInfo:
    """A single Android Virtual Device, as reported by ``avdmanager``/``emulator``.

    Attributes:
        name: The AVD's unique name.
        device: The hardware/skin profile the AVD was built from, when known.
        target: The Android target/API the AVD was built for, when known.
        abi: The system image ABI, when known.
        path: Filesystem path to the AVD's directory.
        valid: Whether the AVD loaded without error. Broken AVDs (bad
            ``config.ini``, missing system image) are still reported
            rather than silently hidden, with *error* explaining why.
        error: Human-readable reason *valid* is ``False``, else ``None``.
        running: Whether an emulator process is currently running this AVD.
        adb_serial: The ``adb`` serial (e.g. ``"emulator-5554"``) if running.

    """

    name: str
    device: str | None
    target: str | None
    abi: str | None
    path: str
    valid: bool
    error: str | None = None
    running: bool = False
    adb_serial: str | None = None


@dataclass(frozen=True)
class EmulatorInstanceHandle:
    """A running emulator instance's identity, for multi-instance launches.

    Attributes:
        name: The AVD name this instance was launched from.
        adb_serial: The ``adb`` serial (e.g. ``"emulator-5554"``).
        console_port: The emulator console TCP port.
        adb_port: The ADB TCP port (``console_port + 1``).
        pid: The OS process id of the ``emulator`` process.
        log_path: Path to this instance's dedicated log file.
        working_directory: Path to this instance's dedicated working directory.

    """

    name: str
    adb_serial: str
    console_port: int
    adb_port: int
    pid: int
    log_path: str
    working_directory: str
    extra_args: tuple[str, ...] = field(default_factory=tuple)
