"""Host hardware detection: CPU, RAM, and virtualization acceleration.

Used to recommend a sensible :class:`~ugaf.emulator.types.PerformanceProfile`
for the current machine, and to surface *why* an emulator might run
slowly (no hardware acceleration available) rather than leaving that a
mystery. Stdlib-only (``os``/``subprocess``) — no extra dependency
(e.g. ``psutil``) is pulled in for what is a handful of one-shot
lookups, consistent with the framework's minimal-dependency stance.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ugaf.core.logger import Logger, get_logger

__all__ = [
    "HardwareInfo",
    "HardwareDetector",
]


@dataclass(frozen=True)
class HardwareInfo:
    """Detected host hardware and virtualization acceleration capability.

    Attributes:
        cpu_count: Logical CPU core count.
        total_ram_mb: Total physical RAM in megabytes.
        accel_available: Whether the ``emulator`` binary reports a
            usable hardware acceleration backend.
        accel_backend: Name of the active backend (e.g. ``"WHPX"``,
            ``"HAXM"``, ``"KVM"``), when determinable.
        accel_message: The raw message from ``emulator -accel-check``,
            for diagnostics.

    """

    cpu_count: int
    total_ram_mb: int
    accel_available: bool
    accel_backend: str | None
    accel_message: str


class HardwareDetector:
    """Detects host CPU/RAM/virtualization capability and recommends a preset."""

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialize the detector."""
        self._logger = logger or get_logger()

    def detect(self, emulator_path: Path | None = None) -> HardwareInfo:
        """Detect current host hardware and, if given, query acceleration support.

        Args:
            emulator_path: Path to the ``emulator`` executable. When
                given, ``emulator -accel-check`` is run to determine
                real hardware-acceleration availability (WHPX/Hyper-V
                on Windows, HAXM, KVM on Linux, HVF on macOS). When
                omitted, acceleration is reported unavailable rather
                than guessed.

        Returns:
            The detected :class:`HardwareInfo`.

        """
        cpu_count = os.cpu_count() or 1
        total_ram_mb = self._detect_total_ram_mb()
        accel_available, accel_backend, accel_message = self._detect_acceleration(emulator_path)

        info = HardwareInfo(
            cpu_count=cpu_count,
            total_ram_mb=total_ram_mb,
            accel_available=accel_available,
            accel_backend=accel_backend,
            accel_message=accel_message,
        )
        self._logger.info(
            "hardware_detector.detected",
            cpu_count=info.cpu_count,
            total_ram_mb=info.total_ram_mb,
            accel_available=info.accel_available,
            accel_backend=info.accel_backend,
        )
        return info

    def recommend_performance_profile(self, hardware: HardwareInfo) -> str:
        """Recommend a performance preset name based on detected hardware headroom.

        Reserves roughly half of detected CPU/RAM for the host and any
        automation tooling running alongside the emulator, rather than
        recommending the machine's full capacity.

        Returns:
            One of ``"low_end"``, ``"mid_range"``, ``"flagship"``, ``"gaming"``.

        """
        usable_cpu = hardware.cpu_count // 2
        usable_ram_mb = hardware.total_ram_mb // 2

        if usable_cpu >= 8 and usable_ram_mb >= 12288:
            return "gaming"
        if usable_cpu >= 6 and usable_ram_mb >= 8192:
            return "flagship"
        if usable_cpu >= 4 and usable_ram_mb >= 4096:
            return "mid_range"
        return "low_end"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_total_ram_mb(self) -> int:
        """Detect total physical RAM in megabytes, per-OS."""
        try:
            if sys.platform == "win32":
                return self._detect_total_ram_mb_windows()
            if sys.platform == "darwin":
                return self._detect_total_ram_mb_darwin()
            return self._detect_total_ram_mb_linux()
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            self._logger.warning("hardware_detector.ram_detection_failed", error=str(exc))
            return 0

    def _detect_total_ram_mb_windows(self) -> int:
        result = subprocess.run(
            ["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=True,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line) // (1024 * 1024)
        return 0

    def _detect_total_ram_mb_linux(self) -> int:
        meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
        match = re.search(r"MemTotal:\s+(\d+)\s+kB", meminfo)
        return int(match.group(1)) // 1024 if match else 0

    def _detect_total_ram_mb_darwin(self) -> int:
        result = subprocess.run(
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=True,
        )
        return int(result.stdout.strip()) // (1024 * 1024)

    def _detect_acceleration(
        self, emulator_path: Path | None
    ) -> tuple[bool, str | None, str]:
        """Run ``emulator -accel-check`` and interpret its output."""
        if emulator_path is None:
            return False, None, "emulator path not provided; acceleration not checked"
        try:
            result = subprocess.run(
                [str(emulator_path), "-accel-check"],
                capture_output=True,
                text=True,
                timeout=15.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, None, f"emulator -accel-check failed: {exc}"

        output = (result.stdout + result.stderr).strip()
        available = result.returncode == 0 and "usable" in output.lower()
        backend_match = re.search(r"\b(WHPX|HAXM|KVM|HVF|Hyper-?V)\b", output)
        backend = backend_match.group(1) if (available and backend_match) else None
        return available, backend, output
