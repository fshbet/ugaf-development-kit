"""Demo Workflow — end-to-end UGAF Version 0.1 capability demonstration.

Exercises the complete workflow the Version 0.1 goal requires: capture
the screen, find a template image on it, tap the detected location,
swipe, and enter text. Runs safely out of the box against bundled demo
assets (``ImageReplayProvider`` + ``MockInputProvider`` — no real
device required); switch ``config.yaml`` to ``adb`` to drive a real
connected Android device instead, with no code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ugaf.core.config import Config
from ugaf.imaging.manager import ImagingManager
from ugaf.input.manager import InputManager
from ugaf.sdk.context import GameContext
from ugaf.sdk.game import GamePlugin
from ugaf.sdk.metadata import PluginMetadata
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.manager import VisionManager
from ugaf.vision.mock_screenshot import ImageReplayProvider
from ugaf.vision.screenshot_manager import ScreenshotManager

metadata = PluginMetadata(
    name="Demo Workflow",
    id="demo_workflow",
    author="UGAF Team",
    version="1.0.0",
    description=(
        "End-to-end demonstration: capture the screen, find a template image, "
        "tap it, swipe, and enter text."
    ),
    supported_platforms=["windows", "linux", "android"],
    minimum_framework_version="1.0.0",
    capabilities=[],
    priority=100,
)

_ASSETS_DIR = Path(__file__).parent / "assets"


class DemoWorkflowGame(GamePlugin):
    """Runs the full capture -> find -> tap -> swipe -> type workflow once at start."""

    metadata = metadata

    def __init__(self) -> None:
        """Initialize plugin state."""
        self._context: GameContext | None = None
        self._health_status: str = "created"
        self._last_result: dict[str, Any] = {}

    async def initialize(self, context: GameContext) -> None:
        """Store the context and mark as initialized."""
        self._context = context
        self._health_status = "initialized"
        if context.logger is not None:
            context.logger.info("demo_workflow.initialized")

    async def start(self) -> None:
        """Run the full demonstration workflow once."""
        self._health_status = "running"
        assert self._context is not None
        logger = self._context.logger
        assert logger is not None
        container = self._context.service_container
        assert container is not None

        imaging = container.resolve(ImagingManager)

        screenshot = ScreenshotManager(imaging=imaging)
        screenshot.connect_with(
            ImageReplayProvider(imaging, directory=_ASSETS_DIR / "screens", loop=True)
        )
        vision = VisionManager(imaging=imaging, screenshot_provider=screenshot)

        input_config = Config(Path(__file__).parent / "config.yaml")
        input_manager = InputManager(input_config)
        input_manager.connect()

        try:
            # 1. Capture the screen.
            screen = vision.screenshot()
            logger.info("demo_workflow.captured", size=(screen.width, screen.height))

            # 2. Find the "START" button template on it.
            template_path = _ASSETS_DIR / "button_template.png"
            match = vision.find_template(screen, template_path, confidence=0.85)
            if match is None:
                raise ScreenshotError("demo_workflow: button template not found on screen")
            logger.info(
                "demo_workflow.found_template",
                region=str(match.region),
                confidence=match.confidence,
            )

            # 3. Tap the detected location.
            cx, cy = match.center
            input_manager.click(cx, cy)
            logger.info("demo_workflow.tapped", x=cx, y=cy)

            # 4. Swipe.
            input_manager.drag(cx, cy, cx, cy - 300, duration=0.3)
            logger.info("demo_workflow.swiped")

            # 5. Enter text.
            input_manager.type_text("ugaf demo complete")
            logger.info("demo_workflow.typed_text")

            self._last_result = {
                "captured": True,
                "match_region": str(match.region),
                "match_confidence": match.confidence,
                "tapped": (cx, cy),
            }
            self._health_status = "completed"
            logger.info("demo_workflow.completed", **self._last_result)
        finally:
            input_manager.disconnect()

    async def pause(self) -> None:
        """No-op: the demo runs once at start."""

    async def resume(self) -> None:
        """No-op: the demo runs once at start."""

    async def stop(self) -> None:
        """Mark the plugin as stopped."""
        self._health_status = "stopped"
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info("demo_workflow.stopped")

    async def shutdown(self) -> None:
        """Release resources."""
        self._health_status = "shutdown"
        if self._context is not None and self._context.logger is not None:
            self._context.logger.info("demo_workflow.shutdown")

    async def health(self) -> dict[str, Any]:
        """Return the plugin's health status and last workflow result."""
        return {"status": self._health_status, "last_result": self._last_result}
