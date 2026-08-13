"""Single authoritative device lifecycle state machine.

Historically the web control panel tracked device "connectedness" in
two independent places: :class:`~ugaf.platform.device.DeviceStatus`
(live ADB reachability, owned by :class:`~ugaf.device.manager.DeviceManager`)
and a session-local ``dict`` membership check in
:class:`~ugaf.webapp.session.AppSession` (whether an
``InputManager``/``ScreenshotManager`` pair had been constructed).
The two could disagree -- ADB reporting a device online while the
session's dict still (or already) disagreed with it -- producing the
"Status=Online, Connected=No" contradiction along with spurious
HTTP 409s on screenshot capture.

:class:`DeviceLifecycle` replaces both flags with one authoritative,
explicitly-transitioned state per device, per ADR-020. Every
subsystem (the connect pipeline, the screenshot route, the
``/api/devices`` API, the UI) must read state from here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from ugaf.core.logger import Logger, get_logger

__all__ = [
    "DeviceLifecycle",
    "DeviceLifecycleSnapshot",
    "DeviceState",
]


class DeviceState(Enum):
    """The one authoritative lifecycle state a device can be in.

    Attributes:
        DISCOVERED: Seen by ADB but no connect attempt has been made.
        VALIDATING: Pre-flight checks (dependencies, system image)
            running before an emulator process is launched.
        STARTING: A connect/recovery attempt, or an emulator launch,
            has begun.
        WAITING_FOR_ADB: Confirming the device is reachable via ADB.
        BOOTING: Confirming ``sys.boot_completed`` and the launcher
            are up.
        INITIALIZING: Constructing the input/screenshot providers.
        CAPTURING_TEST_FRAME: Verifying the screenshot pipeline with
            a real capture before declaring readiness.
        TESTING_INPUT: Verifying input injection works with a real,
            harmless test tap before declaring readiness.
        READY: The full boot sequence succeeded; safe to serve
            screenshots/input.
        STOPPING: An explicit stop (emulator shutdown) is in progress.
        STOPPED: An explicit stop completed cleanly (distinct from
            ``DISCONNECTED``, which covers session-level teardown with
            no implication the underlying device/emulator was shut
            down).
        DISCONNECTED: No connection has been attempted, or a session
            connection was explicitly torn down.
        ERROR: The most recent connect/recovery/start/stop attempt
            failed.

    """

    DISCOVERED = "discovered"
    VALIDATING = "validating"
    STARTING = "starting"
    WAITING_FOR_ADB = "waiting_for_adb"
    BOOTING = "booting"
    INITIALIZING = "initializing"
    CAPTURING_TEST_FRAME = "capturing_test_frame"
    TESTING_INPUT = "testing_input"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"
    DISCONNECTED = "disconnected"
    ERROR = "error"


_TERMINAL_STATES = frozenset(
    {DeviceState.READY, DeviceState.ERROR, DeviceState.STOPPED, DeviceState.DISCONNECTED}
)

_MAX_HISTORY_PER_DEVICE = 50


@dataclass(frozen=True)
class DeviceLifecycleSnapshot:
    """An immutable point-in-time view of one device's lifecycle state.

    Attributes:
        device_id: The device this snapshot describes.
        state: The authoritative state as of this transition.
        reason: Human-readable cause of the transition.
        owner: Which component drove this transition (e.g.
            ``"AppSession.connect_device"``,
            ``"AndroidPlatformManager.start_virtual_device"``) — makes
            a failure reproducible without needing to guess which code
            path was responsible.
        updated_at: Wall-clock time this transition happened.
        elapsed_seconds: Seconds since this device's current *episode*
            began — reset to zero whenever a transition follows a
            terminal state (``READY``/``ERROR``/``STOPPED``/
            ``DISCONNECTED``) or is the device's first-ever transition,
            so it always measures "how long has this boot/connect
            attempt been running," not wall-clock time since process
            start.

    """

    device_id: str
    state: DeviceState
    reason: str
    owner: str = "unknown"
    updated_at: float = field(default_factory=time.time)
    elapsed_seconds: float = 0.0


class DeviceLifecycle:
    """Owns the one authoritative :class:`DeviceState` per device id.

    Usage::

        lifecycle = DeviceLifecycle()
        lifecycle.transition("emulator-5554", DeviceState.STARTING, "connect requested")
        ...
        lifecycle.transition("emulator-5554", DeviceState.READY, "boot sequence complete")
        lifecycle.is_ready("emulator-5554")  # True

    """

    def __init__(self, logger: Logger | None = None) -> None:
        """Initialize with no devices tracked yet.

        Args:
            logger: Optional logger. Falls back to the default logger.

        """
        self._logger = logger or get_logger()
        self._states: dict[str, DeviceLifecycleSnapshot] = {}
        self._history: dict[str, list[DeviceLifecycleSnapshot]] = {}
        self._episode_start: dict[str, float] = {}

    def get(self, device_id: str) -> DeviceLifecycleSnapshot:
        """Return the current snapshot for *device_id*.

        Devices never explicitly transitioned are reported as
        ``DISCONNECTED`` rather than raising, so callers can always
        safely read a state.
        """
        existing = self._states.get(device_id)
        if existing is not None:
            return existing
        return DeviceLifecycleSnapshot(
            device_id, DeviceState.DISCONNECTED, "no connection attempted"
        )

    def is_ready(self, device_id: str) -> bool:
        """Return whether *device_id* is authoritatively ``READY``."""
        return self.get(device_id).state is DeviceState.READY

    def transition(
        self, device_id: str, state: DeviceState, reason: str, owner: str = "unknown"
    ) -> DeviceLifecycleSnapshot:
        """Move *device_id* to *state*, logging the transition.

        Args:
            device_id: The device transitioning.
            state: The new authoritative state.
            reason: Human-readable cause of the transition (surfaced
                in logs and, for ``ERROR``, in API diagnostics).
            owner: Which component drove this transition (e.g.
                ``"AppSession.connect_device"``) — every lifecycle
                transition must be attributable, per ADR-023's logging
                requirements.

        Returns:
            The new snapshot.

        """
        previous = self._states.get(device_id)
        now = time.time()
        if previous is None or previous.state in _TERMINAL_STATES:
            self._episode_start[device_id] = now
        episode_start = self._episode_start.get(device_id, now)

        snapshot = DeviceLifecycleSnapshot(
            device_id,
            state,
            reason,
            owner=owner,
            updated_at=now,
            elapsed_seconds=now - episode_start,
        )
        self._states[device_id] = snapshot
        history = self._history.setdefault(device_id, [])
        history.append(snapshot)
        del history[:-_MAX_HISTORY_PER_DEVICE]

        self._logger.info(
            "device_lifecycle.transition",
            device=device_id,
            from_state=previous.state.value if previous else None,
            to_state=state.value,
            reason=reason,
            owner=owner,
            elapsed_seconds=round(snapshot.elapsed_seconds, 3),
        )
        return snapshot

    def forget(self, device_id: str) -> None:
        """Discard tracked state and history for *device_id* (e.g. on explicit disconnect)."""
        self._states.pop(device_id, None)
        self._history.pop(device_id, None)
        self._episode_start.pop(device_id, None)

    def all(self) -> dict[str, DeviceLifecycleSnapshot]:
        """Return a copy of every currently tracked device's snapshot."""
        return dict(self._states)

    def history(self, device_id: str) -> list[DeviceLifecycleSnapshot]:
        """Return the current episode's transition history for *device_id*, oldest first.

        Bounded to the most recent :data:`_MAX_HISTORY_PER_DEVICE`
        transitions — enough for a Boot Timeline UI without unbounded
        memory growth across a long-running webapp process.
        """
        return list(self._history.get(device_id, []))
