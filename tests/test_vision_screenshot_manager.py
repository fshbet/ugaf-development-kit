"""Tests for ScreenshotManager."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from ugaf.core.config import Config
from ugaf.imaging.image import Image
from ugaf.platform.registry import AdapterRegistry
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider
from ugaf.vision.screenshot_manager import ScreenshotManager

pytestmark = pytest.mark.asyncio


class _FakeProvider(ScreenshotProvider):
    """Controllable provider: fails a configurable number of times, then succeeds."""

    def __init__(self, imaging: object | None = None, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.calls = 0
        self.region_calls: list[Region] = []
        self.window_calls: list[str] = []

    def capture_full(self) -> Image:
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ScreenshotError("simulated failure")
        return MagicMock(spec=Image)

    def capture_region(self, region: Region) -> Image:
        self.region_calls.append(region)
        return MagicMock(spec=Image)

    def capture_game_window(self, window_title: str) -> Image:
        self.window_calls.append(window_title)
        return MagicMock(spec=Image)


@pytest.fixture
def fresh_registry() -> AdapterRegistry[ScreenshotProvider]:
    reg: AdapterRegistry[ScreenshotProvider] = AdapterRegistry(ScreenshotProvider)  # type: ignore[type-abstract]
    reg.register("fake", _FakeProvider)
    return reg


def _config(**vision_overrides: object) -> Config:
    cfg = Config()
    cfg._data = {"vision": vision_overrides}
    return cfg


class TestConnect:
    async def test_connect_selects_configured_provider(
        self, fresh_registry: AdapterRegistry[ScreenshotProvider]
    ) -> None:
        cfg = _config(screenshot_provider="fake")
        mgr = ScreenshotManager(config=cfg, provider_registry=fresh_registry)
        mgr.connect()
        assert isinstance(mgr.provider, _FakeProvider)

    async def test_connect_without_config_raises(
        self, fresh_registry: AdapterRegistry[ScreenshotProvider]
    ) -> None:
        mgr = ScreenshotManager(config=None, provider_registry=fresh_registry)
        with pytest.raises(ScreenshotError, match="No vision.screenshot_provider"):
            mgr.connect()

    async def test_connect_unknown_provider_raises(
        self, fresh_registry: AdapterRegistry[ScreenshotProvider]
    ) -> None:
        cfg = _config(screenshot_provider="nonexistent")
        mgr = ScreenshotManager(config=cfg, provider_registry=fresh_registry)
        with pytest.raises(ScreenshotError, match="Unknown screenshot provider"):
            mgr.connect()

    async def test_connect_with_bypasses_registry(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)
        assert mgr.provider is provider


class TestCapture:
    async def test_capture_full_without_connect_raises(self) -> None:
        mgr = ScreenshotManager()
        with pytest.raises(ScreenshotError, match="not connected"):
            mgr.capture_full()

    async def test_capture_full_delegates_to_provider(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)
        mgr.capture_full()
        assert provider.calls == 1

    async def test_capture_region_delegates(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)
        region = Region(1, 2, 3, 4)
        mgr.capture_region(region)
        assert provider.region_calls == [region]

    async def test_capture_game_window_delegates(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)
        mgr.capture_game_window("My Game")
        assert provider.window_calls == ["My Game"]


class TestRetry:
    async def test_retries_and_succeeds(self) -> None:
        cfg = _config()
        mgr = ScreenshotManager(config=cfg)
        mgr._retry_count = 3
        mgr._retry_delay = 0.0
        provider = _FakeProvider(fail_times=2)
        mgr.connect_with(provider)

        mgr.capture_full()
        assert provider.calls == 3

    async def test_raises_after_exhausting_retries(self) -> None:
        mgr = ScreenshotManager()
        mgr._retry_count = 2
        mgr._retry_delay = 0.0
        provider = _FakeProvider(fail_times=99)
        mgr.connect_with(provider)

        with pytest.raises(ScreenshotError, match="simulated failure"):
            mgr.capture_full()
        assert mgr.last_capture_error is not None


class TestCache:
    async def test_cache_hit_returns_same_object(self) -> None:
        mgr = ScreenshotManager()
        mgr.connect_with(_FakeProvider())

        first = mgr.capture_full(use_cache=True, max_age=10.0)
        second = mgr.capture_full(use_cache=True, max_age=10.0)
        assert first is second

    async def test_cache_miss_when_stale(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)

        mgr.capture_full(use_cache=True, max_age=0.01)
        time.sleep(0.02)
        mgr.capture_full(use_cache=True, max_age=0.01)
        assert provider.calls == 2

    async def test_invalidate_cache_forces_recapture(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)

        mgr.capture_full(use_cache=True, max_age=10.0)
        mgr.invalidate_cache()
        mgr.capture_full(use_cache=True, max_age=10.0)
        assert provider.calls == 2

    async def test_disconnect_clears_cache(self) -> None:
        mgr = ScreenshotManager()
        provider = _FakeProvider()
        mgr.connect_with(provider)
        mgr.capture_full(use_cache=True, max_age=10.0)
        mgr.disconnect()
        assert mgr.provider is None


class TestAsyncCapture:
    async def test_capture_full_async_returns_frame(self) -> None:
        mgr = ScreenshotManager()
        mgr.connect_with(_FakeProvider())
        frame = await mgr.capture_full_async(timeout=2.0)
        assert frame is not None

    async def test_capture_full_async_times_out(self) -> None:
        class _SlowProvider(_FakeProvider):
            def capture_full(self) -> Image:
                time.sleep(0.5)
                return super().capture_full()

        mgr = ScreenshotManager()
        mgr.connect_with(_SlowProvider())
        with pytest.raises(ScreenshotError, match="timed out"):
            await mgr.capture_full_async(timeout=0.01)
