"""Central device orchestrator.

The Core Engine and game plugins depend only on
:class:`DeviceManager` — never on ADB, UIAutomator2, or any other
transport directly. ``DeviceManager`` owns one or more
:class:`ugaf.platform.device.DeviceProvider` transports, polls them
for device state, publishes lifecycle events, and provides retrying
command execution with transport-level recovery (e.g. restarting a
stuck ADB server).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Protocol, runtime_checkable

from ugaf.core.event_bus import Event, EventBus
from ugaf.core.logger import Logger, get_logger
from ugaf.device.exceptions import DeviceCommandError, DeviceNotConnectedError
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

__all__ = [
    "DeviceManager",
]

DEVICE_DISCOVERED = "device.discovered"
DEVICE_ONLINE = "device.online"
DEVICE_OFFLINE = "device.offline"
DEVICE_UNAUTHORIZED = "device.unauthorized"
DEVICE_LOST = "device.lost"

_STATUS_EVENT: dict[DeviceStatus, str] = {
    DeviceStatus.ONLINE: DEVICE_ONLINE,
    DeviceStatus.OFFLINE: DEVICE_OFFLINE,
    DeviceStatus.UNAUTHORIZED: DEVICE_UNAUTHORIZED,
}


@runtime_checkable
class _ShellCapableTransport(Protocol):
    """Optional capability: a transport that can execute shell commands.

    Kept separate from :class:`DeviceProvider` itself so that
    interface stays narrow (per its own module docstring) — not every
    transport needs to support command execution.
    """

    def shell(self, device_id: str, *args: str) -> str: ...


@runtime_checkable
class _RestartableTransport(Protocol):
    """Optional capability: a transport that can recover from a stuck daemon."""

    def restart_server(self) -> None: ...


@runtime_checkable
class _PropertyCapableTransport(Protocol):
    """Optional capability: a transport that can report per-device properties."""

    def get_properties(self, device_id: str) -> dict[str, str]: ...


class DeviceManager:
    """Orchestrates device discovery, health, and command execution across transports.

    Usage::

        manager = DeviceManager(event_bus=event_bus)
        manager.register_provider("adb", AdbDeviceProvider())
        manager.discover()
        await manager.start_monitoring(interval=5.0)
        output = await manager.execute_shell("emulator-5554", "wm", "size")
        await manager.stop_monitoring()

    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialize an empty Device Manager with no registered transports.

        Args:
            event_bus: Optional event bus for lifecycle event
                publication.
            logger: Optional logger. Falls back to the default logger.

        """
        self._providers: dict[str, DeviceProvider] = {}
        self._devices: dict[str, DeviceInfo] = {}
        self._device_transport: dict[str, str] = {}
        self._event_bus = event_bus
        self._logger = logger or get_logger()
        self._monitor_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Transport registration
    # ------------------------------------------------------------------

    def register_provider(self, name: str, provider: DeviceProvider) -> None:
        """Register a transport under *name*.

        Args:
            name: Short transport identifier (e.g. ``"adb"``).
            provider: The :class:`DeviceProvider` instance.

        Raises:
            ValueError: If *name* is already registered.

        """
        if name in self._providers:
            raise ValueError(f"Transport {name!r} is already registered")
        self._providers[name] = provider

    def unregister_provider(self, name: str) -> None:
        """Remove a previously registered transport.

        Raises:
            KeyError: If *name* is not registered.

        """
        del self._providers[name]

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self, enrich: bool = True) -> list[DeviceInfo]:
        """Poll every registered transport once and update the device snapshot.

        Publishes ``device.discovered``, ``device.online``,
        ``device.offline``, ``device.unauthorized``, and
        ``device.lost`` events for anything that changed since the
        previous call.

        Args:
            enrich: If ``True``, online devices whose transport
                supports :class:`_PropertyCapableTransport` get their
                ``extra`` dict enriched with device properties (e.g.
                Android version).

        Returns:
            The combined list of devices from every transport.

        """
        previous = dict(self._devices)
        current: dict[str, DeviceInfo] = {}
        transport_of: dict[str, str] = {}

        for name, provider in self._providers.items():
            for device in provider.list_devices():
                if enrich and device.status is DeviceStatus.ONLINE:
                    device = self._enrich(provider, device)
                current[device.id] = device
                transport_of[device.id] = name

        self._devices = current
        self._device_transport = transport_of
        self._publish_transitions(previous, current)
        return list(current.values())

    def get_device(self, device_id: str) -> DeviceInfo | None:
        """Return the last known snapshot for *device_id*, or ``None``."""
        return self._devices.get(device_id)

    def list_devices(self) -> list[DeviceInfo]:
        """Return the last known device snapshot without re-polling."""
        return list(self._devices.values())

    def resolve_device(self, configured: str | None = None) -> str:
        """Resolve a single target device id, re-discovering first.

        The single canonical place callers that need exactly one
        device (an :class:`~ugaf.input.manager.InputManager`, an
        :class:`~ugaf.apps.manager.ApplicationManager`, a screenshot
        provider) should use to pick which device to target, instead
        of each re-implementing "use the configured device, or the
        sole online device" independently.

        Args:
            configured: An explicit device id (e.g. from
                ``input.adb.default_device`` config), which always
                wins if given. If ``None``, falls back to the sole
                online device.

        Returns:
            The resolved device id.

        Raises:
            DeviceNotConnectedError: If *configured* is not currently
                online, or if none/more than one device is online and
                no *configured* value was given.

        """
        devices = self.discover()
        online = [d for d in devices if d.status is DeviceStatus.ONLINE]
        online_ids = [d.id for d in online]

        if configured is not None:
            if configured not in online_ids:
                match = next((d for d in devices if d.id == configured), None)
                if match is not None:
                    raise DeviceNotConnectedError(
                        f"Device {configured!r} is {match.status.value} (expected online)"
                    )
                raise DeviceNotConnectedError(f"Device {configured!r} not found")
            return configured

        if len(online) == 1:
            return online[0].id
        if not online:
            raise DeviceNotConnectedError("No online Android devices connected")
        raise DeviceNotConnectedError(
            f"Multiple devices online ({online_ids}); specify one explicitly"
        )

    # ------------------------------------------------------------------
    # Continuous monitoring
    # ------------------------------------------------------------------

    async def start_monitoring(self, interval: float = 5.0) -> None:
        """Start a background task that calls :meth:`discover` every *interval* seconds.

        A no-op if monitoring is already running.
        """
        if self._monitor_task is not None:
            return
        self._monitor_task = asyncio.create_task(self._monitor_loop(interval))

    async def stop_monitoring(self) -> None:
        """Cancel the background monitoring task, if running."""
        if self._monitor_task is None:
            return
        self._monitor_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._monitor_task
        self._monitor_task = None

    async def _monitor_loop(self, interval: float) -> None:
        """Repeatedly call :meth:`discover` until cancelled."""
        while True:
            self.discover()
            await asyncio.sleep(interval)

    # ------------------------------------------------------------------
    # Command execution
    # ------------------------------------------------------------------

    async def execute_shell(
        self,
        device_id: str,
        *args: str,
        retry: int = 1,
    ) -> str:
        """Execute a shell command on *device_id*, retrying with transport recovery.

        If the command fails and the owning transport supports
        :class:`_RestartableTransport` (e.g. ``adb kill-server`` /
        ``adb start-server`` for ADB, the documented fix for a stuck
        daemon), the transport is restarted once and the command is
        retried before giving up.

        Args:
            device_id: The device to target.
            *args: Shell command and arguments.
            retry: Number of restart-and-retry cycles to attempt after
                the first failure.

        Raises:
            DeviceNotConnectedError: If *device_id* is not known or
                its transport does not support shell execution.
            DeviceCommandError: If the command still fails after all
                retries.

        """
        provider = self._resolve_provider(device_id)
        if not isinstance(provider, _ShellCapableTransport):
            raise DeviceNotConnectedError(
                f"Transport for device {device_id!r} does not support shell execution"
            )

        last_exc: Exception | None = None
        for attempt in range(retry + 1):
            try:
                return await asyncio.to_thread(provider.shell, device_id, *args)
            except DeviceCommandError as exc:
                last_exc = exc
                self._logger.warning(
                    "device_manager.shell_attempt_failed",
                    device=device_id,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt < retry and isinstance(provider, _RestartableTransport):
                    await asyncio.to_thread(provider.restart_server)

        assert last_exc is not None
        raise last_exc

    def shell_sync(self, device_id: str, *args: str) -> str:
        """Execute a shell command on *device_id* synchronously, no retries.

        For callers that are themselves synchronous (e.g.
        :class:`~ugaf.webapp.session.AppSession`'s device connect
        pipeline) and need a single direct probe -- e.g. checking
        ``sys.boot_completed`` -- without the async retry/recovery
        machinery of :meth:`execute_shell`.

        Raises:
            DeviceNotConnectedError: If *device_id* is not known or
                its transport does not support shell execution.
            DeviceCommandError: If the command fails.

        """
        provider = self._resolve_provider(device_id)
        if not isinstance(provider, _ShellCapableTransport):
            raise DeviceNotConnectedError(
                f"Transport for device {device_id!r} does not support shell execution"
            )
        return provider.shell(device_id, *args)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_provider(self, device_id: str) -> DeviceProvider:
        """Return the transport that reported *device_id* in the last :meth:`discover` call."""
        transport_name = self._device_transport.get(device_id)
        if transport_name is None:
            raise DeviceNotConnectedError(f"Unknown device: {device_id!r}")
        return self._providers[transport_name]

    def _enrich(self, provider: DeviceProvider, device: DeviceInfo) -> DeviceInfo:
        """Best-effort enrich a device's ``extra`` dict with transport-reported properties."""
        if not isinstance(provider, _PropertyCapableTransport):
            return device
        try:
            properties = provider.get_properties(device.id)
        except Exception:  # noqa: BLE001 - enrichment must never break discovery
            return device
        if not properties:
            return device
        merged = {**properties, **device.extra}
        return DeviceInfo(
            id=device.id,
            name=device.name,
            status=device.status,
            platform=device.platform,
            transport=device.transport,
            extra=merged,
        )

    def _publish_transitions(
        self,
        previous: dict[str, DeviceInfo],
        current: dict[str, DeviceInfo],
    ) -> None:
        """Publish lifecycle events for anything that changed between two snapshots."""
        if self._event_bus is None:
            return

        for device_id, device in current.items():
            old = previous.get(device_id)
            if old is None:
                self._publish(DEVICE_DISCOVERED, device)
                status_event = _STATUS_EVENT.get(device.status)
                if status_event is not None:
                    self._publish(status_event, device)
            elif old.status != device.status:
                status_event = _STATUS_EVENT.get(device.status)
                if status_event is not None:
                    self._publish(status_event, device)

        for device_id, device in previous.items():
            if device_id not in current:
                self._publish(DEVICE_LOST, device)

    def _publish(self, topic: str, device: DeviceInfo) -> None:
        """Best-effort publish of a device event onto the event bus.

        Mirrors the tolerant pattern used by
        :class:`ugaf.plugins.manager.PluginManager` — publishing is
        skipped (not raised) if there is no running event loop, since
        :meth:`discover` is also usable synchronously.
        """
        if self._event_bus is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if loop.is_running():
            loop.create_task(
                self._event_bus.publish(
                    Event(
                        topic=topic,
                        data={
                            "device_id": device.id,
                            "name": device.name,
                            "status": device.status.value,
                            "platform": device.platform,
                            "transport": device.transport,
                        },
                    )
                )
            )
