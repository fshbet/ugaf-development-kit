"""Environment/dependency checking for the Emulator Manager, per-component.

``EmulatorManager.__init__`` already fails fast via
:meth:`~ugaf.emulator.sdk_locator.AndroidSdkLocator.locate` the moment
*any* required tool is missing -- correct for "should construction
succeed at all", but useless for showing a user *which* component is
missing when several might be. :class:`EnvironmentChecker` probes each
component independently (never raising) so the webapp's "Create
Emulator" acceptance checklist (Android Studio / SDK / platform-tools /
emulator.exe / sdkmanager / avdmanager) can show real per-item status
instead of one all-or-nothing error.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ugaf.emulator.exceptions import SdkNotFoundError
from ugaf.emulator.hardware import HardwareDetector
from ugaf.emulator.sdk_locator import AndroidSdkLocator
from ugaf.emulator.studio_locator import AndroidStudioLocator

__all__ = [
    "DependencyReport",
    "DependencyStatus",
    "EnvironmentChecker",
]

# Components required to create/run an AVD via the command-line tools.
# Android Studio itself is deliberately excluded -- see the module and
# AndroidStudioLocator docstrings for why it is checked/displayed but
# never blocking.
_BLOCKING_COMPONENTS = ("sdk", "platform_tools", "emulator", "sdkmanager", "avdmanager")


def _read_pkg_revision_at(package_dir: Path) -> str | None:
    """Read ``Pkg.Revision`` from ``package_dir/source.properties``, if present."""
    props_path = package_dir / "source.properties"
    if not props_path.is_file():
        return None
    try:
        for line in props_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("Pkg.Revision="):
                return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


def _read_pkg_revision(tool_path: Path) -> str | None:
    """Read ``Pkg.Revision`` for the SDK package a tool executable belongs to.

    Every SDK package (platform-tools, emulator, cmdline-tools) ships a
    ``source.properties`` file one or two directories above the actual
    executable -- checked at both depths since ``sdkmanager``/
    ``avdmanager`` live under a ``bin/`` subdirectory while ``adb``/
    ``emulator`` sit directly in their package directory.
    """
    return _read_pkg_revision_at(tool_path.parent) or _read_pkg_revision_at(
        tool_path.parent.parent
    )


@dataclass(frozen=True)
class DependencyStatus:
    """One dependency's detection result.

    Attributes:
        name: Human-readable component name (e.g. ``"Android SDK"``).
        found: Whether the component was detected.
        path: The resolved path, when found.
        detail: When not found, a human-readable explanation of what's
            missing and how to fix it (never a generic message). Empty
            when found.
        version: The component's ``Pkg.Revision`` from its
            ``source.properties``, when the component ships one and it
            could be read. ``None`` when not applicable/found.

    """

    name: str
    found: bool
    path: str | None
    detail: str
    version: str | None = None


@dataclass(frozen=True)
class DependencyReport:
    """Every dependency :class:`EnvironmentChecker` knows how to probe.

    Attributes:
        android_studio: Checked and displayed, but never blocking (see
            module docstring).
        sdk: The Android SDK root itself.
        platform_tools: ``adb`` under the SDK's ``platform-tools/``.
        emulator: The ``emulator`` executable.
        sdkmanager: The ``sdkmanager`` command-line tool.
        avdmanager: The ``avdmanager`` command-line tool.
        cmdline_tools_consistency: Whether the ``cmdline-tools``
            directory layout is unambiguous (a ``latest`` symlink/dir,
            or exactly one versioned dir). Informational, not
            blocking — :meth:`~ugaf.emulator.sdk_locator.AndroidSdkLocator._find_cmdline_tool`
            already picks the highest-versioned dir when ``latest`` is
            absent, but multiple versioned dirs with no ``latest`` is
            worth surfacing since a future SDK update could silently
            change which one wins.
        hypervisor: Whether the host has a usable hardware
            virtualization-acceleration backend (WHPX/Hyper-V/HAXM/KVM/HVF),
            per ``emulator -accel-check``. Informational, not blocking
            — the emulator still runs without it, just far slower.

    """

    android_studio: DependencyStatus
    sdk: DependencyStatus
    platform_tools: DependencyStatus
    emulator: DependencyStatus
    sdkmanager: DependencyStatus
    avdmanager: DependencyStatus
    cmdline_tools_consistency: DependencyStatus
    hypervisor: DependencyStatus

    def _blocking_statuses(self) -> tuple[DependencyStatus, ...]:
        return tuple(getattr(self, name) for name in _BLOCKING_COMPONENTS)

    @property
    def ready(self) -> bool:
        """Whether every component required to create/run an AVD is present."""
        return all(status.found for status in self._blocking_statuses())

    def first_missing(self) -> DependencyStatus | None:
        """Return the first missing *blocking* dependency, in check order, or ``None``."""
        for status in self._blocking_statuses():
            if not status.found:
                return status
        return None

    def as_list(self) -> list[DependencyStatus]:
        """Return every status (including Android Studio) in display order."""
        return [
            self.android_studio,
            self.sdk,
            self.platform_tools,
            self.emulator,
            self.sdkmanager,
            self.avdmanager,
            self.cmdline_tools_consistency,
            self.hypervisor,
        ]


class EnvironmentChecker:
    """Probes every Emulator Manager dependency independently, never raising."""

    def __init__(
        self,
        sdk_locator: AndroidSdkLocator | None = None,
        studio_locator: AndroidStudioLocator | None = None,
        hardware_detector: HardwareDetector | None = None,
    ) -> None:
        """Bind the checker to its locators (all optional, for test injection)."""
        self._sdk_locator = sdk_locator or AndroidSdkLocator()
        self._studio_locator = studio_locator or AndroidStudioLocator()
        self._hardware_detector = hardware_detector or HardwareDetector()

    def check(self, sdk_root_override: str | Path | None = None) -> DependencyReport:
        """Probe every dependency and return a full :class:`DependencyReport`.

        Each component is checked independently: a missing SDK root
        means every downstream tool is reported missing too (there is
        nowhere to look for them), but each is still its own
        :class:`DependencyStatus` with its own explanation.
        """
        sdk_root: Path | None
        try:
            sdk_root = self._sdk_locator.find_sdk_root(sdk_root_override)
            sdk_status = DependencyStatus("Android SDK", True, str(sdk_root), "")
        except SdkNotFoundError as exc:
            sdk_root = None
            sdk_status = DependencyStatus("Android SDK", False, None, str(exc))

        platform_tools_status = self._probe(
            sdk_root, "Platform Tools (adb)", self._sdk_locator.find_adb
        )
        emulator_status = self._probe(
            sdk_root, "Android Emulator (emulator.exe)", self._sdk_locator.find_emulator
        )
        sdkmanager_status = self._probe(sdk_root, "sdkmanager", self._sdk_locator.find_sdkmanager)
        avdmanager_status = self._probe(sdk_root, "avdmanager", self._sdk_locator.find_avdmanager)

        studio_path = self._studio_locator.locate(sdk_root)
        studio_status = DependencyStatus(
            "Android Studio",
            studio_path is not None,
            str(studio_path) if studio_path else None,
            ""
            if studio_path
            else (
                "Android Studio was not found in common install locations. This does "
                "not block creating or running emulators (avdmanager/emulator/"
                "sdkmanager work without the IDE) -- only the 'Open Android Studio' "
                "button needs it. Set ANDROID_STUDIO_HOME if it's installed somewhere "
                "non-standard."
            ),
        )

        cmdline_tools_status = self._check_cmdline_tools_consistency(sdk_root)

        emulator_path = Path(emulator_status.path) if emulator_status.path else None
        hardware = self._hardware_detector.detect(emulator_path)
        hypervisor_status = DependencyStatus(
            "Hypervisor",
            hardware.accel_available,
            hardware.accel_backend,
            ""
            if hardware.accel_available
            else (
                "No usable hardware virtualization backend was detected "
                f"({hardware.accel_message or 'no details available'}). The emulator "
                "will still run, but far slower, in full software emulation. On "
                "Windows, enable the 'Windows Hypervisor Platform' feature; on Linux, "
                "verify KVM (`/dev/kvm`) is accessible; on macOS, HVF requires no "
                "action but only works on Apple hardware."
            ),
        )

        return DependencyReport(
            android_studio=studio_status,
            sdk=sdk_status,
            platform_tools=platform_tools_status,
            emulator=emulator_status,
            sdkmanager=sdkmanager_status,
            avdmanager=avdmanager_status,
            cmdline_tools_consistency=cmdline_tools_status,
            hypervisor=hypervisor_status,
        )

    @staticmethod
    def _check_cmdline_tools_consistency(sdk_root: Path | None) -> DependencyStatus:
        """Flag an ambiguous ``cmdline-tools`` layout: no ``latest``, multiple versions.

        Not blocking -- :class:`~ugaf.emulator.sdk_locator.AndroidSdkLocator`
        already resolves this case deterministically (highest version
        wins) -- but worth surfacing since it means a future SDK
        component update could silently change which ``sdkmanager``/
        ``avdmanager`` version is actually being used.
        """
        name = "Command-line Tools Layout"
        if sdk_root is None:
            return DependencyStatus(
                name, False, None, "Cannot check: no Android SDK root was found."
            )
        cmdline_tools = sdk_root / "cmdline-tools"
        if not cmdline_tools.is_dir():
            return DependencyStatus(
                name, False, None, f"No cmdline-tools directory under {sdk_root}."
            )
        if (cmdline_tools / "latest").is_dir():
            latest = cmdline_tools / "latest"
            return DependencyStatus(
                name, True, str(latest), "", version=_read_pkg_revision_at(latest)
            )

        versioned = [d.name for d in cmdline_tools.iterdir() if d.is_dir() and d.name != "latest"]
        if len(versioned) <= 1:
            return DependencyStatus(name, True, str(cmdline_tools), "")
        return DependencyStatus(
            name,
            False,
            str(cmdline_tools),
            f"Multiple cmdline-tools versions installed ({', '.join(sorted(versioned))}) "
            "with no 'latest' symlink/directory -- the highest version is used, but "
            "this is ambiguous and may change unexpectedly after an SDK update. Install "
            "the 'Android SDK Command-line Tools (latest)' package via Android Studio's "
            "SDK Manager to get a stable 'latest' directory.",
        )

    @staticmethod
    def _probe(
        sdk_root: Path | None, name: str, finder: Callable[[Path], Path]
    ) -> DependencyStatus:
        """Run one SDK-root-relative finder, reporting a clear reason when it can't run at all."""
        if sdk_root is None:
            return DependencyStatus(
                name,
                False,
                None,
                f"Cannot check for {name}: no Android SDK root was found "
                "(see 'Android SDK' above).",
            )
        try:
            path = finder(sdk_root)
            return DependencyStatus(name, True, str(path), "", version=_read_pkg_revision(path))
        except SdkNotFoundError as exc:
            return DependencyStatus(name, False, None, str(exc))
