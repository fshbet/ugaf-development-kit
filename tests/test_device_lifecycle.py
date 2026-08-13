"""Tests for the single-authoritative DeviceLifecycle state machine (ADR-020)."""

from __future__ import annotations

from ugaf.device.lifecycle import DeviceLifecycle, DeviceState


def test_unknown_device_reports_disconnected_without_raising() -> None:
    lifecycle = DeviceLifecycle()
    snapshot = lifecycle.get("never-seen")
    assert snapshot.state is DeviceState.DISCONNECTED
    assert snapshot.device_id == "never-seen"


def test_is_ready_false_before_any_transition() -> None:
    lifecycle = DeviceLifecycle()
    assert lifecycle.is_ready("device-1") is False


def test_transition_updates_state_and_is_ready() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.STARTING, "connect requested")
    assert lifecycle.is_ready("device-1") is False
    assert lifecycle.get("device-1").state is DeviceState.STARTING

    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    assert lifecycle.is_ready("device-1") is True
    assert lifecycle.get("device-1").reason == "boot sequence complete"


def test_transition_to_error_is_not_ready() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    lifecycle.transition("device-1", DeviceState.ERROR, "test screenshot failed")
    assert lifecycle.is_ready("device-1") is False
    assert lifecycle.get("device-1").state is DeviceState.ERROR


def test_forget_resets_to_disconnected() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    lifecycle.forget("device-1")
    assert lifecycle.get("device-1").state is DeviceState.DISCONNECTED


def test_devices_are_tracked_independently() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    lifecycle.transition("device-2", DeviceState.ERROR, "device offline")
    assert lifecycle.is_ready("device-1") is True
    assert lifecycle.is_ready("device-2") is False


def test_all_returns_a_snapshot_copy() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    snapshot = lifecycle.all()
    snapshot["device-1"] = None  # type: ignore[assignment]
    assert lifecycle.get("device-1").state is DeviceState.READY


def test_transition_records_owner() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition(
        "device-1", DeviceState.STARTING, "connect requested", owner="AppSession.connect_device"
    )
    assert lifecycle.get("device-1").owner == "AppSession.connect_device"


def test_transition_defaults_owner_to_unknown() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.STARTING, "connect requested")
    assert lifecycle.get("device-1").owner == "unknown"


def test_elapsed_seconds_accumulates_within_one_episode() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.STARTING, "connect requested")
    second = lifecycle.transition("device-1", DeviceState.WAITING_FOR_ADB, "checking ADB")
    assert second.elapsed_seconds >= 0
    # Both transitions belong to the same episode -- elapsed time is
    # measured from the first, not reset on every transition.
    first_elapsed = lifecycle.history("device-1")[0].elapsed_seconds
    assert second.elapsed_seconds >= first_elapsed


def test_elapsed_seconds_resets_after_a_terminal_state() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.STARTING, "connect requested")
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    # A new episode begins after a terminal state (READY/ERROR/STOPPED/DISCONNECTED).
    restarted = lifecycle.transition("device-1", DeviceState.STARTING, "recovery requested")
    assert restarted.elapsed_seconds < 1.0


def test_history_returns_transitions_in_order() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.STARTING, "connect requested")
    lifecycle.transition("device-1", DeviceState.WAITING_FOR_ADB, "checking ADB")
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    history = lifecycle.history("device-1")
    assert [s.state for s in history] == [
        DeviceState.STARTING,
        DeviceState.WAITING_FOR_ADB,
        DeviceState.READY,
    ]


def test_history_empty_for_unknown_device() -> None:
    lifecycle = DeviceLifecycle()
    assert lifecycle.history("never-seen") == []


def test_forget_clears_history() -> None:
    lifecycle = DeviceLifecycle()
    lifecycle.transition("device-1", DeviceState.READY, "boot sequence complete")
    lifecycle.forget("device-1")
    assert lifecycle.history("device-1") == []
