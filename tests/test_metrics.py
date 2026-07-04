"""Tests for ugaf.core.metrics: MetricsTracker/MetricsSnapshot."""

from __future__ import annotations

import time

from ugaf.core.metrics import MetricsTracker


def test_empty_tracker_returns_zeroed_snapshot() -> None:
    tracker = MetricsTracker()
    snap = tracker.snapshot()
    assert snap.count == 0
    assert snap.fps == 0.0
    assert snap.avg_ms == 0.0
    assert snap.min_ms == 0.0
    assert snap.max_ms == 0.0
    assert snap.last_ms == 0.0


def test_single_sample_has_no_fps_but_has_latency() -> None:
    tracker = MetricsTracker()
    tracker.record(0.05)
    snap = tracker.snapshot()
    assert snap.count == 1
    assert snap.fps == 0.0  # needs >= 2 samples to derive a rate
    assert snap.avg_ms == 50.0
    assert snap.last_ms == 50.0


def test_avg_min_max_last_over_multiple_samples() -> None:
    tracker = MetricsTracker()
    for d in (0.01, 0.02, 0.03):
        tracker.record(d)
    snap = tracker.snapshot()
    assert snap.count == 3
    assert snap.min_ms == 10.0
    assert snap.max_ms == 30.0
    assert snap.last_ms == 30.0
    assert snap.avg_ms == 20.0


def test_window_evicts_oldest_samples() -> None:
    tracker = MetricsTracker(window=2)
    tracker.record(0.01)
    tracker.record(0.02)
    tracker.record(0.03)
    snap = tracker.snapshot()
    assert snap.count == 2
    assert snap.min_ms == 20.0
    assert snap.max_ms == 30.0


def test_measure_context_manager_records_duration() -> None:
    tracker = MetricsTracker()
    with tracker.measure():
        time.sleep(0.01)
    snap = tracker.snapshot()
    assert snap.count == 1
    assert snap.last_ms >= 10.0


def test_measure_records_even_when_body_raises() -> None:
    tracker = MetricsTracker()
    try:
        with tracker.measure():
            raise ValueError("boom")
    except ValueError:
        pass
    assert tracker.snapshot().count == 1


def test_reset_clears_samples() -> None:
    tracker = MetricsTracker()
    tracker.record(0.01)
    tracker.reset()
    assert tracker.snapshot().count == 0


def test_fps_reflects_sample_rate() -> None:
    tracker = MetricsTracker()
    tracker.record(0.001)
    time.sleep(0.1)
    tracker.record(0.001)
    snap = tracker.snapshot()
    # Two samples ~0.1s apart -> ~10 fps.
    assert 5.0 < snap.fps < 20.0


def test_as_dict_is_json_friendly_and_rounded() -> None:
    tracker = MetricsTracker()
    tracker.record(0.0123456)
    snap = tracker.snapshot()
    d = snap.as_dict()
    assert d["count"] == 1
    assert isinstance(d["avg_ms"], float)
    assert d["avg_ms"] == round(12.3456, 2)
