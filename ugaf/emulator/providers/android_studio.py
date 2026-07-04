"""Android Studio emulator provider: drives real ``avdmanager``/``emulator``/``adb``.

The first and, today, only :class:`~ugaf.emulator.provider.EmulatorProvider`
implementation — everything else (:class:`~ugaf.emulator.manager.EmulatorManager`,
the webapp) talks only to the abstract interface, so a future provider
(BlueStacks, LDPlayer, Genymotion, ...) plugs in without touching this
module or its callers.
"""

from __future__ import annotations

import builtins
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ugaf.core.logger import Logger, get_logger
from ugaf.emulator._avd_config import read_avd_config, write_avd_config
from ugaf.emulator.android_versions import AndroidVersionManager
from ugaf.emulator.exceptions import (
    AvdAlreadyExistsError,
    AvdNotFoundError,
    EmulatorCommandError,
)
from ugaf.emulator.provider import EmulatorProvider
from ugaf.emulator.sdk_locator import AndroidSdkPaths
from ugaf.emulator.types import AvdInfo, DeviceProfile, EmulatorInstanceHandle, PerformanceProfile

__all__ = [
    "AndroidStudioProvider",
]

_FIELD_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /]*):\s*(.*)$")
_TAG_ABI_RE = re.compile(r"Tag/ABI:\s*([\w_.-]+)/([\w-]+)")
_INSTANCES_DIR = Path.home() / ".ugaf" / "emulator_instances"


@dataclass
class _RunningInstance:
    """Bookkeeping for one emulator process this provider launched."""

    handle: EmulatorInstanceHandle
    process: subprocess.Popen[bytes]
    log_file: object
    stopped_intentionally: bool = False


class AndroidStudioProvider(EmulatorProvider):
    """Manages AVDs and emulator processes via the official Android SDK command-line tools."""

    def __init__(
        self,
        sdk_paths: AndroidSdkPaths,
        android_versions: AndroidVersionManager,
        logger: Logger | None = None,
        first_console_port: int = 5554,
        tool_timeout: float = 30.0,
    ) -> None:
        """Bind the provider to a resolved SDK installation.

        Args:
            sdk_paths: Resolved SDK tool paths.
            android_versions: Used by :meth:`create` to ensure the
                requested system image is installed before building the AVD.
            logger: Optional logger.
            first_console_port: The first console port to try when
                allocating a port pair for a new instance (subsequent
                instances use the next free even port).
            tool_timeout: Timeout in seconds for ``avdmanager``/``adb``
                invocations (not ``emulator`` itself, which is
                long-running and never awaited synchronously).

        """
        self._sdk_paths = sdk_paths
        self._android_versions = android_versions
        self._logger = logger or get_logger()
        self._first_console_port = first_console_port
        self._tool_timeout = tool_timeout
        self._instances: dict[str, _RunningInstance] = {}

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def list(self) -> list[AvdInfo]:
        """Return every AVD reported by ``avdmanager list avd``, valid or broken.

        Running state is cross-referenced against ``adb devices`` so
        that instances started outside this provider (e.g. from
        Android Studio directly) are still correctly reported.
        """
        result = self._run(self._sdk_paths.avdmanager, "list", "avd")
        infos = self._parse_avd_list(result.stdout)

        running_by_name: dict[str, str] = {}
        for serial in self._list_adb_emulator_serials():
            name = self._query_running_avd_name(serial)
            if name is not None:
                running_by_name[name] = serial

        return [
            AvdInfo(
                name=info.name,
                device=info.device,
                target=info.target,
                abi=info.abi,
                path=info.path,
                valid=info.valid,
                error=info.error,
                running=info.name in running_by_name,
                adb_serial=running_by_name.get(info.name),
            )
            for info in infos
        ]

    def is_running(self, name: str) -> bool:
        """Return whether *name* currently has a running emulator process."""
        return self._find_running_serial(name) is not None

    def detect_crash(self, name: str) -> bool:
        """Return whether an instance this provider launched has exited unexpectedly."""
        instance = self._instances.get(name)
        if instance is None:
            return False
        if instance.stopped_intentionally:
            return False
        return instance.process.poll() is not None

    def wait_until_booted(self, name: str, timeout: float) -> bool:
        """Poll ``sys.boot_completed`` until it reports ``1``, or *timeout* elapses."""
        deadline = time.monotonic() + timeout
        serial = self._find_running_serial(name)
        if serial is None:
            self._logger.warning("android_studio_provider.wait_boot_not_running", name=name)
            return False

        while time.monotonic() < deadline:
            try:
                result = self._run(
                    self._sdk_paths.adb, "-s", serial, "shell", "getprop", "sys.boot_completed"
                )
            except EmulatorCommandError:
                result = None
            if result is not None and result.stdout.strip() == "1":
                self._logger.info("android_studio_provider.boot_completed", name=name)
                return True
            time.sleep(2.0)

        self._logger.warning("android_studio_provider.boot_timeout", name=name, timeout=timeout)
        return False

    # ------------------------------------------------------------------
    # Lifecycle: create / delete / rename / clone / update
    # ------------------------------------------------------------------

    def create(
        self,
        name: str,
        device_profile: DeviceProfile,
        performance_profile: PerformanceProfile,
        force: bool = False,
    ) -> AvdInfo:
        """Create a new AVD, ensuring its system image is installed first."""
        existing = {info.name: info for info in self.list()}
        if name in existing and not force:
            raise AvdAlreadyExistsError(f"AVD {name!r} already exists")

        tag = "google_apis_playstore" if device_profile.play_store else "google_apis"
        system_image = self._android_versions.ensure_installed(
            device_profile.api_level, tag=tag, abi=device_profile.abi
        )

        self._logger.info(
            "android_studio_provider.creating",
            name=name,
            device=device_profile.device_name,
            api_level=device_profile.api_level,
        )
        args = [
            "create",
            "avd",
            "--name",
            name,
            "--package",
            system_image.package_path,
            "--device",
            device_profile.hardware_name,
        ]
        if force:
            args.append("--force")
        self._run(self._sdk_paths.avdmanager, *args, stdin_text="no\n")

        self._apply_device_profile(name, device_profile)
        self.update_hardware(name, performance_profile)

        self._logger.info("android_studio_provider.created", name=name)
        return self._require_avd(name)

    def delete(self, name: str) -> None:
        """Stop (if running) and permanently delete an AVD."""
        if self.is_running(name):
            self.stop(name)
        self._logger.info("android_studio_provider.deleting", name=name)
        self._run(self._sdk_paths.avdmanager, "delete", "avd", "--name", name)
        self._instances.pop(name, None)

    def rename(self, name: str, new_name: str) -> None:
        """Rename an AVD by moving its directory and rewriting its ``.ini`` pointer file."""
        avd_dir = self._sdk_paths.avd_home / f"{name}.avd"
        ini_path = self._sdk_paths.avd_home / f"{name}.ini"
        if not avd_dir.is_dir() or not ini_path.is_file():
            raise AvdNotFoundError(f"AVD {name!r} not found")

        new_avd_dir = self._sdk_paths.avd_home / f"{new_name}.avd"
        new_ini_path = self._sdk_paths.avd_home / f"{new_name}.ini"
        if new_avd_dir.exists() or new_ini_path.exists():
            raise AvdAlreadyExistsError(f"AVD {new_name!r} already exists")

        shutil.move(str(avd_dir), str(new_avd_dir))
        shutil.move(str(ini_path), str(new_ini_path))
        self._rewrite_ini_pointer(new_ini_path, new_avd_dir)
        self._rewrite_config_identity(new_avd_dir, new_name)
        self._logger.info("android_studio_provider.renamed", old=name, new=new_name)

    def clone(self, source: str, target: str) -> AvdInfo:
        """Copy an AVD's directory and ``.ini`` file under a new name."""
        source_dir = self._sdk_paths.avd_home / f"{source}.avd"
        source_ini = self._sdk_paths.avd_home / f"{source}.ini"
        if not source_dir.is_dir() or not source_ini.is_file():
            raise AvdNotFoundError(f"AVD {source!r} not found")

        target_dir = self._sdk_paths.avd_home / f"{target}.avd"
        target_ini = self._sdk_paths.avd_home / f"{target}.ini"
        if target_dir.exists() or target_ini.exists():
            raise AvdAlreadyExistsError(f"AVD {target!r} already exists")

        shutil.copytree(source_dir, target_dir)
        shutil.copy2(source_ini, target_ini)
        self._rewrite_ini_pointer(target_ini, target_dir)
        self._rewrite_config_identity(target_dir, target)
        self._logger.info("android_studio_provider.cloned", source=source, target=target)
        return self._require_avd(target)

    def update_hardware(self, name: str, performance_profile: PerformanceProfile) -> None:
        """Rewrite an AVD's ``config.ini`` to reflect a new performance profile."""
        config_path = self._sdk_paths.avd_home / f"{name}.avd" / "config.ini"
        if not config_path.is_file():
            raise AvdNotFoundError(f"AVD {name!r} not found")

        config = read_avd_config(config_path)
        config["hw.cpu.ncore"] = str(performance_profile.cpu_count)
        config["hw.ramSize"] = f"{performance_profile.ram_mb}"
        config["vm.heapSize"] = str(performance_profile.heap_mb)
        config["disk.dataPartition.size"] = f"{performance_profile.storage_mb}M"
        config["hw.gpu.enabled"] = "yes" if performance_profile.gpu_mode != "off" else "no"
        config["hw.gpu.mode"] = performance_profile.gpu_mode
        config["runtime.network.speed"] = performance_profile.network_speed
        config["fastboot.forceColdBoot"] = "no" if performance_profile.snapshot_enabled else "yes"
        if performance_profile.resolution is not None:
            width, height = performance_profile.resolution
            config["hw.lcd.width"] = str(width)
            config["hw.lcd.height"] = str(height)

        write_avd_config(config_path, config)
        self._logger.info(
            "android_studio_provider.hardware_updated",
            name=name,
            profile=performance_profile.name,
        )

    # ------------------------------------------------------------------
    # Running instances
    # ------------------------------------------------------------------

    def start(self, name: str) -> EmulatorInstanceHandle:
        """Launch an AVD as a new emulator process with a freshly allocated port pair."""
        avd = self._require_avd(name)
        if not avd.valid:
            raise EmulatorCommandError(f"AVD {name!r} is broken: {avd.error}")

        console_port = self._allocate_console_port()
        adb_serial = f"emulator-{console_port}"
        workdir = _INSTANCES_DIR / f"{name}_{console_port}"
        workdir.mkdir(parents=True, exist_ok=True)
        log_path = workdir / "emulator.log"

        args = [str(self._sdk_paths.emulator), "-avd", name, "-port", str(console_port)]
        log_file = log_path.open("ab")
        self._logger.info(
            "android_studio_provider.starting",
            name=name,
            console_port=console_port,
            adb_serial=adb_serial,
        )
        process = subprocess.Popen(
            args,
            cwd=str(workdir),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

        handle = EmulatorInstanceHandle(
            name=name,
            adb_serial=adb_serial,
            console_port=console_port,
            adb_port=console_port + 1,
            pid=process.pid,
            log_path=str(log_path),
            working_directory=str(workdir),
        )
        self._instances[name] = _RunningInstance(handle=handle, process=process, log_file=log_file)
        return handle

    def stop(self, name: str) -> None:
        """Gracefully shut down a running AVD (via ``adb emu kill``, falling back to terminate)."""
        instance = self._instances.get(name)
        serial = (
            instance.handle.adb_serial if instance is not None else self._find_running_serial(name)
        )
        if serial is None:
            self._logger.info("android_studio_provider.stop_not_running", name=name)
            return

        self._logger.info("android_studio_provider.stopping", name=name, serial=serial)
        if instance is not None:
            instance.stopped_intentionally = True
        try:
            self._run(self._sdk_paths.adb, "-s", serial, "emu", "kill")
        except EmulatorCommandError:
            pass

        if instance is not None:
            try:
                instance.process.wait(timeout=15.0)
            except subprocess.TimeoutExpired:
                instance.process.terminate()
                try:
                    instance.process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    instance.process.kill()
            if hasattr(instance.log_file, "close"):
                instance.log_file.close()
            del self._instances[name]
        self._logger.info("android_studio_provider.stopped", name=name)

    # ------------------------------------------------------------------
    # Data transfer
    # ------------------------------------------------------------------

    def install_apk(self, name: str, apk_path: Path | str) -> None:
        """Install an APK onto a running AVD."""
        serial = self._require_running_serial(name)
        self._run(self._sdk_paths.adb, "-s", serial, "install", "-r", str(apk_path))

    def push(self, name: str, source: Path | str, destination: str) -> None:
        """Push a file to a running AVD."""
        serial = self._require_running_serial(name)
        self._run(self._sdk_paths.adb, "-s", serial, "push", str(source), destination)

    def pull(self, name: str, source: str, destination: Path | str) -> None:
        """Pull a file from a running AVD."""
        serial = self._require_running_serial(name)
        self._run(self._sdk_paths.adb, "-s", serial, "pull", source, str(destination))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_avd(self, name: str) -> AvdInfo:
        for info in self.list():
            if info.name == name:
                return info
        raise AvdNotFoundError(f"AVD {name!r} not found")

    def _require_running_serial(self, name: str) -> str:
        serial = self._find_running_serial(name)
        if serial is None:
            raise EmulatorCommandError(f"AVD {name!r} is not running")
        return serial

    def _find_running_serial(self, name: str) -> str | None:
        instance = self._instances.get(name)
        if instance is not None and instance.process.poll() is None:
            return instance.handle.adb_serial

        for serial in self._list_adb_emulator_serials():
            if self._query_running_avd_name(serial) == name:
                return serial
        return None

    def _list_adb_emulator_serials(self) -> builtins.list[str]:
        try:
            result = self._run(self._sdk_paths.adb, "devices")
        except EmulatorCommandError:
            return []
        serials = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if parts and parts[0].startswith("emulator-"):
                serials.append(parts[0])
        return serials

    def _query_running_avd_name(self, serial: str) -> str | None:
        try:
            result = self._run(self._sdk_paths.adb, "-s", serial, "emu", "avd", "name")
        except EmulatorCommandError:
            return None
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return lines[0] if lines and lines[0] != "OK" else None

    def _allocate_console_port(self) -> int:
        used = {instance.handle.console_port for instance in self._instances.values()}
        for serial in self._list_adb_emulator_serials():
            try:
                used.add(int(serial.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
        port = self._first_console_port
        while port in used:
            port += 2
        return port

    def _apply_device_profile(self, name: str, device_profile: DeviceProfile) -> None:
        """Apply a device profile's identity/resolution/DPI fields to a freshly created AVD."""
        config_path = self._sdk_paths.avd_home / f"{name}.avd" / "config.ini"
        config = read_avd_config(config_path)
        width, height = device_profile.resolution
        config["hw.lcd.width"] = str(width)
        config["hw.lcd.height"] = str(height)
        config["hw.lcd.density"] = str(device_profile.dpi)
        config["PlayStore.enabled"] = "yes" if device_profile.play_store else "no"
        write_avd_config(config_path, config)

    def _rewrite_ini_pointer(self, ini_path: Path, avd_dir: Path) -> None:
        """Update an AVD's ``.ini`` pointer file after a rename/clone moved its directory."""
        config = read_avd_config(ini_path)
        config["path"] = str(avd_dir)
        avd_home = self._sdk_paths.avd_home
        try:
            config["path.rel"] = str(avd_dir.relative_to(avd_home.parent))
        except ValueError:
            config.pop("path.rel", None)
        write_avd_config(ini_path, config)

    def _rewrite_config_identity(self, avd_dir: Path, new_name: str) -> None:
        """Update an AVD's own ``config.ini`` identity fields after a rename/clone."""
        config_path = avd_dir / "config.ini"
        if not config_path.is_file():
            return
        config = read_avd_config(config_path)
        config["avd.id"] = new_name
        config["avd.name"] = new_name
        write_avd_config(config_path, config)

    def _parse_avd_list(self, output: str) -> builtins.list[AvdInfo]:
        """Parse ``avdmanager list avd`` text output into :class:`AvdInfo` entries."""
        infos: builtins.list[AvdInfo] = []
        current: dict[str, str] = {}
        valid = True

        def flush() -> None:
            nonlocal current
            if current.get("Name"):
                tag_abi_source = current.get("Based on") or current.get("Target") or ""
                abi_match = _TAG_ABI_RE.search(tag_abi_source)
                infos.append(
                    AvdInfo(
                        name=current["Name"],
                        device=current.get("Device"),
                        target=current.get("Target"),
                        abi=abi_match.group(2) if abi_match else None,
                        path=current.get("Path", ""),
                        valid=valid,
                        error=current.get("Error"),
                    )
                )
            current = {}

        for raw_line in output.splitlines():
            stripped = raw_line.strip()
            if not stripped or stripped == "---------":
                flush()
                continue
            if stripped.lower().startswith("available android virtual devices"):
                flush()
                valid = True
                continue
            if stripped.lower().startswith("the following android virtual devices"):
                flush()
                valid = False
                continue
            match = _FIELD_RE.match(raw_line)
            if match is None:
                continue
            current[match.group(1).strip()] = match.group(2).strip()
        flush()
        return infos

    def _run(
        self, executable: Path, *args: str, stdin_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run a short-lived SDK tool, translating failures into framework exceptions."""
        try:
            result = subprocess.run(
                [str(executable), *args],
                input=stdin_text,
                capture_output=True,
                text=True,
                timeout=self._tool_timeout,
            )
        except FileNotFoundError as exc:
            raise EmulatorCommandError(f"{executable} not found") from exc
        except subprocess.TimeoutExpired as exc:
            raise EmulatorCommandError(f"{executable} {' '.join(args)} timed out") from exc

        if result.returncode != 0:
            raise EmulatorCommandError(
                f"{executable.name} {' '.join(args)} failed "
                f"(exit {result.returncode}): {result.stderr.strip()}"
            )
        return result
