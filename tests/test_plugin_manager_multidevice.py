"""Tests for PluginManager's device_id-parametrized multi-instance lifecycle.

Proves the core multi-device scheduling guarantee: the *same*
automation can run as several independent, concurrent instances (one
per target device), each with its own state and logs, and a failure in
one instance never affects another — without needing real hardware,
using a small in-memory ``GamePlugin`` double.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ugaf.core.config import Config
from ugaf.plugins.manager import PluginManager
from ugaf.plugins.registry import PluginRegistry
from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState

pytestmark = pytest.mark.asyncio

_META = PluginMetadata(name="Device Aware", id="device_aware", author="Test", version="1.0.0")


class _DeviceAwarePlugin(GamePlugin):
    """Records the device_id it was given and its own call history.

    ``fail_on`` lets a single instance be scripted to fail a specific
    lifecycle step, independent of any other instance of the same
    plugin class.
    """

    metadata = _META

    def __init__(self) -> None:
        self.seen_device_id: str | None = None
        self.calls: list[str] = []
        self.fail_on: str | None = None
        self.cycles_run = 0

    async def initialize(self, context: GameContext) -> None:
        self.seen_device_id = context.device_id
        self.calls.append("initialize")

    async def start(self) -> None:
        self.calls.append("start")
        if self.fail_on == "start":
            raise RuntimeError(f"boom on {self.seen_device_id}")
        self.cycles_run += 1

    async def pause(self) -> None:
        self.calls.append("pause")

    async def resume(self) -> None:
        self.calls.append("resume")

    async def stop(self) -> None:
        self.calls.append("stop")
        if self.fail_on == "stop":
            raise RuntimeError(f"boom on {self.seen_device_id}")

    async def shutdown(self) -> None:
        self.calls.append("shutdown")

    async def health(self) -> dict[str, Any]:
        return {"device_id": self.seen_device_id, "cycles_run": self.cycles_run}


@pytest.fixture
def manager() -> PluginManager:
    registry = PluginRegistry()
    registry.register(_META, _DeviceAwarePlugin)
    return PluginManager(config=Config(), registry=registry)


class TestDeviceScopedInstances:
    async def test_no_device_id_preserves_single_shared_instance(
        self, manager: PluginManager
    ) -> None:
        """Default (device_id=None) behaviour is completely unchanged."""
        lc1 = manager.load("device_aware")
        lc2 = manager.load("device_aware")
        assert lc1 is lc2
        assert manager.lifecycles.keys() == {"device_aware"}

    async def test_different_device_ids_create_independent_instances(
        self, manager: PluginManager
    ) -> None:
        lc_a = manager.load("device_aware", device_id="deviceA")
        lc_b = manager.load("device_aware", device_id="deviceB")
        assert lc_a is not lc_b
        assert lc_a.plugin is not lc_b.plugin
        assert set(manager.lifecycles.keys()) == {"device_aware@deviceA", "device_aware@deviceB"}

    async def test_same_device_id_reuses_the_same_instance(self, manager: PluginManager) -> None:
        lc1 = manager.load("device_aware", device_id="deviceA")
        lc2 = manager.load("device_aware", device_id="deviceA")
        assert lc1 is lc2

    async def test_each_instance_receives_its_own_device_id_in_context(
        self, manager: PluginManager
    ) -> None:
        await manager.initialize("device_aware", device_id="deviceA")
        await manager.initialize("device_aware", device_id="deviceB")

        plugin_a = manager.lifecycles["device_aware@deviceA"].plugin
        plugin_b = manager.lifecycles["device_aware@deviceB"].plugin
        assert isinstance(plugin_a, _DeviceAwarePlugin)
        assert isinstance(plugin_b, _DeviceAwarePlugin)
        assert plugin_a.seen_device_id == "deviceA"
        assert plugin_b.seen_device_id == "deviceB"

    async def test_instances_run_concurrently_with_independent_state(
        self, manager: PluginManager
    ) -> None:
        await manager.initialize("device_aware", device_id="deviceA")
        await manager.initialize("device_aware", device_id="deviceB")

        await asyncio.gather(
            manager.start("device_aware", device_id="deviceA"),
            manager.start("device_aware", device_id="deviceB"),
        )

        health_a = await manager.health("device_aware", device_id="deviceA")
        health_b = await manager.health("device_aware", device_id="deviceB")
        assert health_a["device_id"] == "deviceA"
        assert health_a["cycles_run"] == 1
        assert health_b["device_id"] == "deviceB"
        assert health_b["cycles_run"] == 1

    async def test_failure_on_one_device_does_not_affect_another(
        self, manager: PluginManager
    ) -> None:
        """A failure in one device-bound instance must not stop the others."""
        await manager.initialize("device_aware", device_id="deviceA")
        await manager.initialize("device_aware", device_id="deviceB")

        plugin_a = manager.lifecycles["device_aware@deviceA"].plugin
        assert isinstance(plugin_a, _DeviceAwarePlugin)
        plugin_a.fail_on = "start"

        results = await asyncio.gather(
            manager.start("device_aware", device_id="deviceA"),
            manager.start("device_aware", device_id="deviceB"),
            return_exceptions=True,
        )

        assert isinstance(results[0], RuntimeError)
        assert results[1] is None

        lifecycle_a = manager.lifecycles["device_aware@deviceA"]
        lifecycle_b = manager.lifecycles["device_aware@deviceB"]
        assert lifecycle_a.state is GameState.ERROR
        assert lifecycle_b.state is GameState.RUNNING

        health_b = await manager.health("device_aware", device_id="deviceB")
        assert health_b["cycles_run"] == 1

    async def test_stop_all_is_fault_isolated_across_device_instances(
        self, manager: PluginManager
    ) -> None:
        await manager.initialize("device_aware", device_id="deviceA")
        await manager.initialize("device_aware", device_id="deviceB")
        await manager.start("device_aware", device_id="deviceA")
        await manager.start("device_aware", device_id="deviceB")

        plugin_a = manager.lifecycles["device_aware@deviceA"].plugin
        assert isinstance(plugin_a, _DeviceAwarePlugin)
        plugin_a.fail_on = "stop"

        await manager.stop_all()  # must not raise, despite deviceA's stop() failing

        assert manager.lifecycles["device_aware@deviceA"].state is GameState.ERROR
        assert manager.lifecycles["device_aware@deviceB"].state is GameState.STOPPED
