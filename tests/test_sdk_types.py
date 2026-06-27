"""Tests for SDK types: Capabilities, GameState, PluginMetadata, GameContext."""

from __future__ import annotations

import pytest

from ugaf.sdk.capabilities import Capability
from ugaf.sdk.context import GameContext
from ugaf.sdk.exceptions import PluginStateError
from ugaf.sdk.metadata import PluginMetadata
from ugaf.sdk.state import GameState, is_valid_transition, validate_transition


class TestCapability:
    def test_values(self) -> None:
        assert Capability.INPUT.value == "input"
        assert Capability.VISION.value == "vision"
        assert Capability.OCR.value == "ocr"
        assert Capability.SCREENSHOT.value == "screenshot"
        assert Capability.MULTI_DEVICE.value == "multi_device"
        assert Capability.ADB.value == "adb"
        assert Capability.WINDOWS.value == "windows"

    def test_from_string(self) -> None:
        assert Capability("input") is Capability.INPUT
        assert Capability("vision") is Capability.VISION

    def test_all_members(self) -> None:
        assert len(Capability) == 7


class TestGameState:
    def test_values(self) -> None:
        assert GameState.CREATED.value == "created"
        assert GameState.INITIALIZED.value == "initialized"
        assert GameState.RUNNING.value == "running"
        assert GameState.PAUSED.value == "paused"
        assert GameState.STOPPED.value == "stopped"
        assert GameState.ERROR.value == "error"
        assert GameState.SHUTDOWN.value == "shutdown"

    def test_all_members(self) -> None:
        assert len(GameState) == 7


class TestTransitions:
    def test_created_to_initialized(self) -> None:
        assert is_valid_transition(GameState.CREATED, GameState.INITIALIZED)

    def test_created_to_shutdown(self) -> None:
        assert is_valid_transition(GameState.CREATED, GameState.SHUTDOWN)

    def test_initialized_to_running(self) -> None:
        assert is_valid_transition(GameState.INITIALIZED, GameState.RUNNING)

    def test_running_to_paused(self) -> None:
        assert is_valid_transition(GameState.RUNNING, GameState.PAUSED)

    def test_running_to_stopped(self) -> None:
        assert is_valid_transition(GameState.RUNNING, GameState.STOPPED)

    def test_paused_to_running(self) -> None:
        assert is_valid_transition(GameState.PAUSED, GameState.RUNNING)

    def test_paused_to_stopped(self) -> None:
        assert is_valid_transition(GameState.PAUSED, GameState.STOPPED)

    def test_stopped_to_running(self) -> None:
        assert is_valid_transition(GameState.STOPPED, GameState.RUNNING)

    def test_stopped_to_shutdown(self) -> None:
        assert is_valid_transition(GameState.STOPPED, GameState.SHUTDOWN)

    def test_error_to_created(self) -> None:
        assert is_valid_transition(GameState.ERROR, GameState.CREATED)

    def test_error_to_shutdown(self) -> None:
        assert is_valid_transition(GameState.ERROR, GameState.SHUTDOWN)

    def test_shutdown_no_transitions(self) -> None:
        for state in GameState:
            if state is GameState.SHUTDOWN:
                continue
            assert not is_valid_transition(GameState.SHUTDOWN, state)

    def test_invalid_transition(self) -> None:
        assert not is_valid_transition(GameState.CREATED, GameState.RUNNING)

    def test_validate_transition_passes(self) -> None:
        validate_transition(GameState.CREATED, GameState.INITIALIZED)

    def test_validate_transition_raises(self) -> None:
        with pytest.raises(PluginStateError, match="Cannot transition"):
            validate_transition(GameState.CREATED, GameState.RUNNING)


class TestPluginMetadata:
    def test_defaults(self) -> None:
        meta = PluginMetadata(name="Test", id="test", author="Me", version="1.0.0")
        assert meta.description == ""
        assert meta.supported_platforms == []
        assert meta.minimum_framework_version == "1.0.0"
        assert meta.capabilities == []
        assert meta.priority == 100

    def test_frozen(self) -> None:
        meta = PluginMetadata(name="Test", id="test", author="Me", version="1.0.0")
        with pytest.raises(AttributeError):
            meta.name = "changed"  # type: ignore[misc]

    def test_full_init(self) -> None:
        meta = PluginMetadata(
            name="Full Test",
            id="full_test",
            author="Author",
            version="2.0.0",
            description="A full test",
            supported_platforms=["windows"],
            minimum_framework_version="1.0.0",
            capabilities=[Capability.INPUT],
            priority=50,
        )
        assert meta.name == "Full Test"
        assert meta.id == "full_test"
        assert meta.author == "Author"
        assert meta.version == "2.0.0"
        assert meta.description == "A full test"
        assert meta.supported_platforms == ["windows"]
        assert meta.capabilities == [Capability.INPUT]
        assert meta.priority == 50


class TestGameContext:
    def test_minimal(self) -> None:
        ctx = GameContext(config={}, logger=None, event_bus=None)  # type: ignore[arg-type]
        assert ctx.config == {}
        assert ctx.logger is None
        assert ctx.event_bus is None
        assert ctx.service_container is None
        assert ctx.extra == {}

    def test_extra_dict(self) -> None:
        ctx = GameContext(config={}, logger=None, event_bus=None, extra={"key": "val"})
        assert ctx.extra["key"] == "val"
