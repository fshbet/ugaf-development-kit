"""Reusable performance-metrics tracking for capture, processing, and input.

A single small primitive (:class:`MetricsTracker`) covers every "how fast is
this" question the platform needs to answer — capture FPS, end-to-end capture
latency, vision frame-processing time, input latency — rather than one
bespoke counter per subsystem. Any component that does repeated timed work
can own one and expose its :meth:`MetricsTracker.snapshot` for the UI.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

__all__ = [
    "MetricsSnapshot",
    "MetricsTracker",
]


@dataclass(frozen=True)
class MetricsSnapshot:
    """A point-in-time read of a :class:`MetricsTracker`'s rolling window.

    Attributes:
        count: Number of samples currently in the window.
        fps: Samples per second, derived from the timestamp span of the
            window (0.0 if fewer than two samples are recorded).
        avg_ms: Average sample duration in milliseconds.
        min_ms: Minimum sample duration in milliseconds.
        max_ms: Maximum sample duration in milliseconds.
        last_ms: Most recently recorded duration in milliseconds.

    """

    count: int
    fps: float
    avg_ms: float
    min_ms: float
    max_ms: float
    last_ms: float

    def as_dict(self) -> dict[str, float | int]:
        """Return a JSON-friendly dict (for the webapp's metrics endpoint)."""
        return {
            "count": self.count,
            "fps": round(self.fps, 2),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
            "last_ms": round(self.last_ms, 2),
        }


_EMPTY_SNAPSHOT = MetricsSnapshot(count=0, fps=0.0, avg_ms=0.0, min_ms=0.0, max_ms=0.0, last_ms=0.0)


class MetricsTracker:
    """Tracks a rolling window of timed samples and reports FPS/latency.

    Usage::

        tracker = MetricsTracker()
        with tracker.measure():
            do_the_timed_work()
        tracker.snapshot()  # -> MetricsSnapshot

    """

    def __init__(self, window: int = 60) -> None:
        """Initialize the tracker.

        Args:
            window: Number of most-recent samples to keep. Older
                samples are dropped as new ones arrive.

        """
        self._durations: deque[float] = deque(maxlen=window)
        self._timestamps: deque[float] = deque(maxlen=window)

    def record(self, duration_seconds: float) -> None:
        """Record one completed operation's duration."""
        self._durations.append(duration_seconds)
        self._timestamps.append(time.monotonic())

    @contextmanager
    def measure(self) -> Iterator[None]:
        """Context manager that times its body and records the duration."""
        start = time.monotonic()
        try:
            yield
        finally:
            self.record(time.monotonic() - start)

    def snapshot(self) -> MetricsSnapshot:
        """Return the current rolling-window metrics."""
        if not self._durations:
            return _EMPTY_SNAPSHOT

        durations_ms = [d * 1000.0 for d in self._durations]
        fps = 0.0
        if len(self._timestamps) >= 2:
            span = self._timestamps[-1] - self._timestamps[0]
            if span > 0:
                fps = (len(self._timestamps) - 1) / span

        return MetricsSnapshot(
            count=len(durations_ms),
            fps=fps,
            avg_ms=sum(durations_ms) / len(durations_ms),
            min_ms=min(durations_ms),
            max_ms=max(durations_ms),
            last_ms=durations_ms[-1],
        )

    def reset(self) -> None:
        """Discard all recorded samples."""
        self._durations.clear()
        self._timestamps.clear()
