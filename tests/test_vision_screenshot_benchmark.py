"""Lightweight capture-cache benchmark.

Not a rigorous perf-lab benchmark — a sanity check that caching
actually avoids redundant capture work, cheap enough to run as part of
the normal test suite rather than a separate opt-in benchmark job.
"""

from __future__ import annotations

import time

from ugaf.imaging.manager import ImagingManager
from ugaf.vision.mock_screenshot import MockScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager


class _CountingProvider(MockScreenshotProvider):
    def __init__(self, imaging: ImagingManager) -> None:
        super().__init__(imaging, width=1080, height=1920)
        self.capture_count = 0

    def capture_full(self):  # type: ignore[no-untyped-def]
        self.capture_count += 1
        return super().capture_full()


def test_cache_reduces_capture_count_under_repeated_calls() -> None:
    """100 calls with a 1s cache window should hit the provider exactly once."""
    imaging = ImagingManager()
    provider = _CountingProvider(imaging)
    mgr = ScreenshotManager()
    mgr.connect_with(provider)

    start = time.perf_counter()
    for _ in range(100):
        mgr.capture_full(use_cache=True, max_age=1.0)
    elapsed = time.perf_counter() - start

    assert provider.capture_count == 1
    # 100 cache hits against a synthetic in-memory provider should be fast;
    # a generous bound avoids flakiness on slow CI runners while still
    # catching an accidental cache-bypass regression.
    assert elapsed < 1.0


def test_no_cache_captures_every_call() -> None:
    imaging = ImagingManager()
    provider = _CountingProvider(imaging)
    mgr = ScreenshotManager()
    mgr.connect_with(provider)

    for _ in range(10):
        mgr.capture_full(use_cache=False)

    assert provider.capture_count == 10
