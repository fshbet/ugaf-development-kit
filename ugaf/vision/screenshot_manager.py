"""Screenshot manager: selects, connects, caches, and retries screen capture.

Mirrors the pattern already established by
:class:`ugaf.input.manager.InputManager` (provider selection via a
registry + config, bounded retry) and
:class:`ugaf.device.manager.DeviceManager` (async wrapping of a
synchronous provider call with a timeout).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from ugaf.core.logger import Logger, get_logger
from ugaf.core.metrics import MetricsSnapshot, MetricsTracker
from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.platform.registry import AdapterRegistry
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.region import Region
from ugaf.vision.screenshot import ScreenshotProvider

if TYPE_CHECKING:
    from ugaf.core.config import Config

__all__ = [
    "ScreenshotManager",
    "registry",
]

# ScreenshotProvider is intentionally abstract — see the identical pattern (and
# rationale for the type: ignore) in ugaf/platform/__init__.py, ADR-008.
registry: AdapterRegistry[ScreenshotProvider] = AdapterRegistry(
    ScreenshotProvider  # type: ignore[type-abstract]
)


class ScreenshotManager(ScreenshotProvider):
    """Manages screenshot providers with caching, retry, and async capture.

    Subclasses :class:`~ugaf.vision.screenshot.ScreenshotProvider` —
    its ``capture_full``/``capture_region``/``capture_game_window``
    methods satisfy the interface (with additional optional caching
    parameters on ``capture_full``), so a :class:`ScreenshotManager`
    can be passed anywhere a plain provider is expected (e.g.
    :class:`~ugaf.vision.manager.VisionManager`'s
    ``screenshot_provider`` argument), transparently adding retry and
    caching to whichever concrete provider it wraps.

    Usage::

        mgr = ScreenshotManager(config)
        mgr.connect()
        frame = mgr.capture_full()

        # Async, with a timeout:
        frame = await mgr.capture_full_async(timeout=2.0)

        # Reuse a recent frame instead of re-capturing:
        frame = mgr.capture_full(use_cache=True, max_age=0.1)

    """

    def __init__(
        self,
        config: Config | None = None,
        imaging: ImagingManager | None = None,
        provider_registry: AdapterRegistry[ScreenshotProvider] | None = None,
        logger: Logger | None = None,
    ) -> None:
        """Initialize the screenshot manager.

        Args:
            config: Framework configuration. Reads
                ``vision.screenshot_provider`` for provider selection
                and ``vision.screenshot.retry.{count,delay}`` for
                retry behavior.
            imaging: Optional :class:`~ugaf.imaging.manager.ImagingManager`.
                Creates a default one if not provided.
            provider_registry: Optional provider registry. Defaults to
                the module-level :data:`registry` singleton.
            logger: Optional logger.

        """
        self._config = config
        self._imaging = imaging or ImagingManager(config=config)
        self._registry = provider_registry or registry
        self._provider: ScreenshotProvider | None = None
        self._logger = logger or get_logger()
        self._retry_count = int(config.get("vision.screenshot.retry.count", 2)) if config else 2
        self._retry_delay = (
            float(config.get("vision.screenshot.retry.delay", 0.2)) if config else 0.2
        )
        self._cached_frame: Image | None = None
        self._cached_at: float = 0.0
        self._last_capture_error: Exception | None = None
        self._metrics = MetricsTracker()

    @property
    def provider(self) -> ScreenshotProvider | None:
        """Return the currently selected provider, if connected."""
        return self._provider

    @property
    def last_capture_error(self) -> Exception | None:
        """Return the most recent capture failure, or ``None``.

        Useful for a caller (or future telemetry) to inspect the last
        failure without needing to catch every exception from
        :meth:`capture_full` itself.
        """
        return self._last_capture_error

    @property
    def metrics(self) -> MetricsSnapshot:
        """Return capture performance metrics (FPS, latency) for the current provider.

        Measures wall-clock time for each real (non-cache-hit) capture,
        over a rolling window — the same number regardless of which
        :class:`~ugaf.vision.screenshot.ScreenshotProvider` is
        connected, so callers (and the web UI) can compare ADB,
        scrcpy, and window-capture transports on equal footing.
        """
        return self._metrics.snapshot()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def connect(self, **provider_kwargs: object) -> None:
        """Select and construct the configured screenshot provider.

        Reads ``vision.screenshot_provider`` from configuration.

        Args:
            **provider_kwargs: Extra keyword arguments forwarded to the
                provider's constructor (e.g. ``device_id`` for
                :class:`~ugaf.vision.adb_screenshot.AdbScreenshotProvider`).

        Raises:
            ScreenshotError: If no provider is configured, or the
                configured provider name is not registered.

        """
        provider_name = self._config.get("vision.screenshot_provider") if self._config else None
        if provider_name is None:
            raise ScreenshotError(
                "No vision.screenshot_provider configured — set it in config "
                "or call connect_with(provider) directly"
            )
        try:
            self._provider = self._registry.create(
                str(provider_name), imaging=self._imaging, **provider_kwargs
            )
        except KeyError as exc:
            raise ScreenshotError(f"Unknown screenshot provider: {provider_name!r}") from exc

    def connect_with(self, provider: ScreenshotProvider) -> None:
        """Use an already-constructed provider directly, bypassing the registry."""
        self._provider = provider

    def disconnect(self) -> None:
        """Release the current provider and clear the frame cache."""
        self._provider = None
        self.invalidate_cache()

    def invalidate_cache(self) -> None:
        """Discard the cached frame, forcing the next capture to be fresh."""
        self._cached_frame = None
        self._cached_at = 0.0

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------

    def capture_full(self, use_cache: bool = False, max_age: float = 0.0) -> Image:
        """Capture the full screen, retrying on failure.

        Args:
            use_cache: If ``True``, return the cached frame instead of
                capturing when it is younger than *max_age*.
            max_age: Maximum cache age in seconds. Ignored unless
                *use_cache* is ``True``.

        Raises:
            ScreenshotError: If not connected, or capture fails after
                all retries.

        """
        if use_cache and self._cached_frame is not None:
            age = time.monotonic() - self._cached_at
            if age <= max_age:
                return self._cached_frame

        image = self._capture_with_retry(lambda p: p.capture_full())
        self._cached_frame = image
        self._cached_at = time.monotonic()
        return image

    def capture_region(self, region: Region) -> Image:
        """Capture a specific screen region, retrying on failure."""
        return self._capture_with_retry(lambda p: p.capture_region(region))

    def capture_game_window(self, window_title: str) -> Image:
        """Capture a game window by title, retrying on failure."""
        return self._capture_with_retry(lambda p: p.capture_game_window(window_title))

    async def capture_full_async(
        self,
        timeout: float | None = None,
        use_cache: bool = False,
        max_age: float = 0.0,
    ) -> Image:
        """Capture the full screen off the event loop, with an optional timeout.

        Args:
            timeout: Maximum time in seconds to wait, or ``None`` to
                wait indefinitely.
            use_cache: See :meth:`capture_full`.
            max_age: See :meth:`capture_full`.

        Raises:
            ScreenshotError: If capture fails, or times out.

        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.capture_full, use_cache=use_cache, max_age=max_age),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise ScreenshotError(f"Screenshot capture timed out after {timeout}s") from exc

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _capture_with_retry(self, action: Callable[[ScreenshotProvider], Image]) -> Image:
        """Execute a capture action against the provider, retrying on failure.

        Raises:
            ScreenshotError: If not connected, or every attempt fails.

        """
        if self._provider is None:
            raise ScreenshotError("ScreenshotManager is not connected")

        last_exc: Exception | None = None
        for attempt in range(1, self._retry_count + 1):
            try:
                with self._metrics.measure():
                    return action(self._provider)
            except ScreenshotError as exc:
                last_exc = exc
                self._last_capture_error = exc
                self._logger.warning(
                    "screenshot.capture_attempt_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < self._retry_count:
                    time.sleep(self._retry_delay)

        assert last_exc is not None
        raise last_exc
