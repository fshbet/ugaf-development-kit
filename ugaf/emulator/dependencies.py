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

    """

    name: str
    found: bool
    path: str | None
    detail: str


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

    """

    android_studio: DependencyStatus
    sdk: DependencyStatus
    platform_tools: DependencyStatus
    emulator: DependencyStatus
    sdkmanager: DependencyStatus
    avdmanager: DependencyStatus

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
        ]


class EnvironmentChecker:
    """Probes every Emulator Manager dependency independently, never raising."""

    def __init__(
        self,
        sdk_locator: AndroidSdkLocator | None = None,
        studio_locator: AndroidStudioLocator | None = None,
    ) -> None:
        """Bind the checker to its locators (both optional, for test injection)."""
        self._sdk_locator = sdk_locator or AndroidSdkLocator()
        self._studio_locator = studio_locator or AndroidStudioLocator()

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

        return DependencyReport(
            android_studio=studio_status,
            sdk=sdk_status,
            platform_tools=platform_tools_status,
            emulator=emulator_status,
            sdkmanager=sdkmanager_status,
            avdmanager=avdmanager_status,
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
            return DependencyStatus(name, True, str(path), "")
        except SdkNotFoundError as exc:
            return DependencyStatus(name, False, None, str(exc))
