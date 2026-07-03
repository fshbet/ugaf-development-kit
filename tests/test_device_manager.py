"""Tests for DeviceManager."""

from __future__ import annotations

import asyncio

import pytest

from ugaf.core.event_bus import EventBus
from ugaf.device.exceptions import DeviceCommandError, DeviceNotConnectedError
from ugaf.device.manager import DeviceManager
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus


class _FakeProvider(DeviceProvider):
    """In-memory DeviceProvider for testing orchestration logic."""

    def __init__(self) -> None:
        self.devices: list[DeviceInfo] = []
        self.shell_calls: list[tuple[str, tuple[str, ...]]] = []
        self.restart_calls = 0
        self.fail_shell_times = 0

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    def get_device(self, device_id: str) -> DeviceInfo | None:
        for d in self.devices:
            if d.id == device_id:
                return d
        return None

    def shell(self, device_id: str, *args: str) -> str:
        self.shell_calls.append((device_id, args))
        if self.fail_shell_times > 0:
            self.fail_shell_times -= 1
            raise DeviceCommandError("simulated failure")
        return "ok"

    def restart_server(self) -> None:
        self.restart_calls += 1


class _PropertyProvider(DeviceProvider):
    """Provider with get_properties() to test enrichment."""

    def __init__(self, properties: dict[str, str], raise_error: bool = False) -> None:
        self._properties = properties
        self._raise_error = raise_error
        self.devices = [
            DeviceInfo(
                id="propdev", name="X", status=DeviceStatus.ONLINE, platform="x", transport="x"
            )
        ]

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return self.devices[0] if device_id == "propdev" else None

    def get_properties(self, device_id: str) -> dict[str, str]:
        if self._raise_error:
            raise RuntimeError("boom")
        return self._properties


class _NonShellProvider(DeviceProvider):
    """Provider without shell()/restart_server() to test capability checks."""

    def list_devices(self) -> list[DeviceInfo]:
        return [
            DeviceInfo(
                id="noshell1", name="X", status=DeviceStatus.ONLINE, platform="x", transport="x"
            )
        ]

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return self.list_devices()[0] if device_id == "noshell1" else None


def _device(device_id: str, status: DeviceStatus) -> DeviceInfo:
    return DeviceInfo(
        id=device_id, name="Fake", status=status, platform="android", transport="fake"
    )


class TestProviderRegistration:
    def test_register_and_unregister(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        mgr.register_provider("fake", provider)
        mgr.unregister_provider("fake")
        mgr.register_provider("fake", provider)  # should not raise after unregister

    def test_register_duplicate_raises(self) -> None:
        mgr = DeviceManager()
        mgr.register_provider("fake", _FakeProvider())
        with pytest.raises(ValueError, match="already registered"):
            mgr.register_provider("fake", _FakeProvider())

    def test_unregister_missing_raises(self) -> None:
        mgr = DeviceManager()
        with pytest.raises(KeyError):
            mgr.unregister_provider("missing")


class TestDiscover:
    def test_discover_combines_all_providers(self) -> None:
        mgr = DeviceManager()
        p1, p2 = _FakeProvider(), _FakeProvider()
        p1.devices = [_device("d1", DeviceStatus.ONLINE)]
        p2.devices = [_device("d2", DeviceStatus.OFFLINE)]
        mgr.register_provider("p1", p1)
        mgr.register_provider("p2", p2)

        devices = mgr.discover()
        ids = {d.id for d in devices}
        assert ids == {"d1", "d2"}

    def test_list_devices_returns_last_snapshot(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()

        provider.devices = []  # change underlying state without re-discovering
        assert len(mgr.list_devices()) == 1

    def test_get_device_returns_snapshot_entry(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()

        assert mgr.get_device("d1") is not None
        assert mgr.get_device("missing") is None

    def test_discover_without_enrichment(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        devices = mgr.discover(enrich=False)
        assert devices[0].extra == {}

    def test_discover_enriches_online_devices_with_properties(self) -> None:
        mgr = DeviceManager()
        provider = _PropertyProvider({"ro.build.version.release": "14"})
        mgr.register_provider("prop", provider)

        devices = mgr.discover(enrich=True)
        assert devices[0].extra["ro.build.version.release"] == "14"

    def test_discover_enrichment_failure_is_swallowed(self) -> None:
        mgr = DeviceManager()
        provider = _PropertyProvider({}, raise_error=True)
        mgr.register_provider("prop", provider)

        devices = mgr.discover(enrich=True)  # should not raise
        assert devices[0].extra == {}

    def test_discover_enrichment_with_empty_properties_leaves_device_unchanged(self) -> None:
        mgr = DeviceManager()
        provider = _PropertyProvider({})
        mgr.register_provider("prop", provider)

        devices = mgr.discover(enrich=True)
        assert devices[0].extra == {}

    def test_discover_skips_enrichment_for_offline_devices(self) -> None:
        mgr = DeviceManager()
        provider = _PropertyProvider({"key": "value"})
        provider.devices = [_device("d1", DeviceStatus.OFFLINE)]
        mgr.register_provider("prop", provider)

        devices = mgr.discover(enrich=True)
        assert devices[0].extra == {}


class TestEventPublication:
    @pytest.mark.asyncio
    async def test_discovered_and_online_events(self) -> None:
        bus = EventBus()
        events: list[str] = []

        async def tracker(event: object) -> None:
            events.append(event.topic)  # type: ignore[attr-defined]

        await bus.subscribe("device.**", tracker)
        mgr = DeviceManager(event_bus=bus)
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)

        mgr.discover()
        await asyncio.sleep(0.05)

        assert "device.discovered" in events
        assert "device.online" in events

    @pytest.mark.asyncio
    async def test_status_transition_publishes_event(self) -> None:
        bus = EventBus()
        events: list[str] = []

        async def tracker(event: object) -> None:
            events.append(event.topic)  # type: ignore[attr-defined]

        await bus.subscribe("device.**", tracker)
        mgr = DeviceManager(event_bus=bus)
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()
        await asyncio.sleep(0.05)
        events.clear()

        provider.devices = [_device("d1", DeviceStatus.OFFLINE)]
        mgr.discover()
        await asyncio.sleep(0.05)

        assert events == ["device.offline"]

    @pytest.mark.asyncio
    async def test_device_lost_publishes_event(self) -> None:
        bus = EventBus()
        events: list[str] = []

        async def tracker(event: object) -> None:
            events.append(event.topic)  # type: ignore[attr-defined]

        await bus.subscribe("device.**", tracker)
        mgr = DeviceManager(event_bus=bus)
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()
        await asyncio.sleep(0.05)
        events.clear()

        provider.devices = []
        mgr.discover()
        await asyncio.sleep(0.05)

        assert events == ["device.lost"]

    def test_discover_without_event_bus_does_not_raise(self) -> None:
        mgr = DeviceManager(event_bus=None)
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()  # should not raise

    def test_discover_with_event_bus_but_no_running_loop_does_not_raise(self) -> None:
        """discover() is usable synchronously; publishing is skipped, not raised."""
        bus = EventBus()
        mgr = DeviceManager(event_bus=bus)
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()  # no running event loop in this (non-async) test


class TestExecuteShell:
    @pytest.mark.asyncio
    async def test_execute_shell_success(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)
        mgr.discover()

        result = await mgr.execute_shell("d1", "echo", "hi")
        assert result == "ok"
        assert provider.shell_calls == [("d1", ("echo", "hi"))]

    @pytest.mark.asyncio
    async def test_execute_shell_retries_with_restart(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        provider.fail_shell_times = 1
        mgr.register_provider("fake", provider)
        mgr.discover()

        result = await mgr.execute_shell("d1", "echo", "hi", retry=1)
        assert result == "ok"
        assert provider.restart_calls == 1

    @pytest.mark.asyncio
    async def test_execute_shell_raises_after_exhausting_retries(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        provider.fail_shell_times = 99
        mgr.register_provider("fake", provider)
        mgr.discover()

        with pytest.raises(DeviceCommandError, match="simulated failure"):
            await mgr.execute_shell("d1", "echo", "hi", retry=1)

    @pytest.mark.asyncio
    async def test_execute_shell_unknown_device_raises(self) -> None:
        mgr = DeviceManager()
        with pytest.raises(DeviceNotConnectedError, match="Unknown device"):
            await mgr.execute_shell("missing", "echo")

    @pytest.mark.asyncio
    async def test_execute_shell_unsupported_transport_raises(self) -> None:
        mgr = DeviceManager()
        mgr.register_provider("noshell", _NonShellProvider())
        mgr.discover()

        with pytest.raises(DeviceNotConnectedError, match="does not support shell"):
            await mgr.execute_shell("noshell1", "echo")


class TestMonitoring:
    @pytest.mark.asyncio
    async def test_start_and_stop_monitoring(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)

        await mgr.start_monitoring(interval=0.01)
        await asyncio.sleep(0.05)
        await mgr.stop_monitoring()

        assert len(mgr.list_devices()) == 1

    @pytest.mark.asyncio
    async def test_start_monitoring_is_idempotent(self) -> None:
        mgr = DeviceManager()
        await mgr.start_monitoring(interval=1.0)
        task = mgr._monitor_task
        await mgr.start_monitoring(interval=1.0)
        assert mgr._monitor_task is task
        await mgr.stop_monitoring()

    @pytest.mark.asyncio
    async def test_stop_monitoring_without_start_is_noop(self) -> None:
        mgr = DeviceManager()
        await mgr.stop_monitoring()  # should not raise


class TestResolveDevice:
    def test_resolves_sole_online_device(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)

        assert mgr.resolve_device() == "d1"

    def test_configured_device_wins_even_with_others_online(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE), _device("d2", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)

        assert mgr.resolve_device(configured="d2") == "d2"

    def test_configured_device_not_online_raises_with_its_status(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.OFFLINE)]
        mgr.register_provider("fake", provider)

        with pytest.raises(DeviceNotConnectedError, match="offline"):
            mgr.resolve_device(configured="d1")

    def test_configured_device_unknown_raises_not_found(self) -> None:
        mgr = DeviceManager()
        mgr.register_provider("fake", _FakeProvider())

        with pytest.raises(DeviceNotConnectedError, match="not found"):
            mgr.resolve_device(configured="ghost")

    def test_no_devices_online_raises(self) -> None:
        mgr = DeviceManager()
        mgr.register_provider("fake", _FakeProvider())

        with pytest.raises(DeviceNotConnectedError, match="No online"):
            mgr.resolve_device()

    def test_multiple_devices_online_without_configured_raises(self) -> None:
        mgr = DeviceManager()
        provider = _FakeProvider()
        provider.devices = [_device("d1", DeviceStatus.ONLINE), _device("d2", DeviceStatus.ONLINE)]
        mgr.register_provider("fake", provider)

        with pytest.raises(DeviceNotConnectedError, match="Multiple devices online"):
            mgr.resolve_device()
