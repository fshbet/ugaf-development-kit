"""Tests for the PluginRegistry."""

from __future__ import annotations

import pytest

from ugaf.plugins.registry import PluginRegistry
from ugaf.sdk.capabilities import Capability
from ugaf.sdk.exceptions import PluginValidationError
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata


def _make_meta(
    name: str,
    plugin_id: str,
    capabilities: list[Capability] | None = None,
    priority: int = 100,
) -> PluginMetadata:
    return PluginMetadata(
        name=name,
        id=plugin_id,
        author="Test",
        version="1.0.0",
        capabilities=capabilities or [],
        priority=priority,
    )


class TestPluginRegistry:
    def test_empty(self) -> None:
        reg = PluginRegistry()
        assert reg.count == 0
        assert reg.list() == []

    def test_register_and_find(self) -> None:
        reg = PluginRegistry()
        meta = _make_meta("Test", "test")
        reg.register(meta, _DummyPlugin)
        assert reg.find("test") is _DummyPlugin

    def test_register_duplicate_id_raises(self) -> None:
        reg = PluginRegistry()
        reg.register(_make_meta("First", "dup"), _DummyPlugin)
        with pytest.raises(PluginValidationError, match="already registered"):
            reg.register(_make_meta("Second", "dup"), _DummyPlugin)

    def test_register_duplicate_name_raises(self) -> None:
        reg = PluginRegistry()
        reg.register(_make_meta("Same", "first"), _DummyPlugin)
        with pytest.raises(PluginValidationError, match="already registered"):
            reg.register(_make_meta("Same", "second"), _DummyPlugin)

    def test_unregister_removes(self) -> None:
        reg = PluginRegistry()
        reg.register(_make_meta("Test", "test"), _DummyPlugin)
        reg.unregister("test")
        assert reg.find("test") is None
        assert reg.count == 0

    def test_unregister_unknown_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")

    def test_find_returns_none_for_missing(self) -> None:
        reg = PluginRegistry()
        assert reg.find("missing") is None

    def test_find_by_capability(self) -> None:
        reg = PluginRegistry()
        input_meta = _make_meta("Input", "input_p", capabilities=[Capability.INPUT])
        vision_meta = _make_meta("Vision", "vision_p", capabilities=[Capability.VISION])
        both_meta = _make_meta("Both", "both_p", capabilities=[Capability.INPUT, Capability.VISION])
        reg.register(input_meta, _DummyPlugin)
        reg.register(vision_meta, _DummyPlugin)
        reg.register(both_meta, _DummyPlugin)

        results = reg.find_by_capability(Capability.INPUT)
        assert len(results) == 2
        result_ids = {r[0].id for r in results}
        assert result_ids == {"input_p", "both_p"}

    def test_find_by_capability_no_match(self) -> None:
        reg = PluginRegistry()
        reg.register(_make_meta("NoCap", "nocap"), _DummyPlugin)
        results = reg.find_by_capability(Capability.OCR)
        assert results == []

    def test_list_sorted_by_priority_then_name(self) -> None:
        reg = PluginRegistry()
        reg.register(_make_meta("Zeta", "z", priority=200), _DummyPlugin)
        reg.register(_make_meta("Alpha", "a", priority=100), _DummyPlugin)
        reg.register(_make_meta("Beta", "b", priority=100), _DummyPlugin)

        names = [m.name for m in reg.list()]
        assert names == ["Alpha", "Beta", "Zeta"]

    def test_count(self) -> None:
        reg = PluginRegistry()
        assert reg.count == 0
        reg.register(_make_meta("A", "a"), _DummyPlugin)
        assert reg.count == 1
        reg.register(_make_meta("B", "b"), _DummyPlugin)
        assert reg.count == 2

    def test_thread_safety(self) -> None:
        import threading

        reg = PluginRegistry()
        errors: list[Exception] = []
        lock = threading.Lock()

        def _register(n: int) -> None:
            try:
                reg.register(
                    _make_meta(f"T{n}", f"t{n}"),
                    _DummyPlugin,
                )
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=_register, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert reg.count == 10


class _DummyPlugin(GamePlugin):
    metadata = PluginMetadata(name="Dummy", id="dummy", author="Test", version="0.0.0")

    async def initialize(self, context: object) -> None: ...
    async def start(self) -> None: ...
    async def pause(self) -> None: ...
    async def resume(self) -> None: ...
    async def stop(self) -> None: ...
    async def shutdown(self) -> None: ...
    async def health(self) -> dict:  # type: ignore[type-arg]
        return {}
