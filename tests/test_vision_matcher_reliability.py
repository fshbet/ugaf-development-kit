"""Template matching reliability tests against realistic rendered images.

The original repository audit flagged that no test in the vision suite
ever exercised real OpenCV computation against non-trivial pixel data
— matcher/detector tests used zero-filled numpy arrays with mocked
backends. These tests use the real OpenCV backend against rendered
"screen" images with gradients, noise, and drawn UI elements (not an
actual physical device capture, since none is available in this
environment — see ``games/demo_workflow`` for how the same code path
runs against a real device when one is connected), which is what
actually exercises ``cv2.matchTemplate`` against realistic content.
"""

from __future__ import annotations

import numpy
import pytest

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.matcher import TemplateMatcher


@pytest.fixture
def imaging() -> ImagingManager:
    return ImagingManager()


def _render_screen(imaging: ImagingManager, seed: int = 0) -> Image:
    """Render a realistic (non-zero, non-uniform) 800x400 phone-screen-like image."""
    rng = numpy.random.default_rng(seed)
    # Gradient background + noise, not a flat/zero array.
    gradient = numpy.linspace(30, 90, 400, dtype=numpy.uint8)
    data = numpy.tile(gradient[:, None, None], (1, 800, 3)).astype(numpy.uint8)
    noise = rng.integers(0, 15, size=data.shape, dtype=numpy.uint8)
    data = numpy.clip(data.astype(numpy.int16) + noise, 0, 255).astype(numpy.uint8)
    return Image(data, imaging.backend)


def _draw_button(screen: Image, x: int, y: int, w: int, h: int, label: str) -> Image:
    """Draw a realistic-looking UI button (filled rect + border + text) at a known position."""
    return (
        screen.draw_rectangle(x, y, w, h, color=(60, 140, 60), thickness=-1)
        .draw_rectangle(x, y, w, h, color=(20, 90, 20), thickness=2)
        .draw_text(label, x + 10, y + h - 15, font_scale=0.7, color=(255, 255, 255), thickness=2)
    )


class TestExactMatch:
    def test_finds_button_at_correct_pixel_location(self, imaging: ImagingManager) -> None:
        screen = _render_screen(imaging)
        button_x, button_y, button_w, button_h = 320, 180, 160, 60
        screen = _draw_button(screen, button_x, button_y, button_w, button_h, "START")
        template = screen.crop(button_x, button_y, button_w, button_h)

        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(screen, template, confidence=0.9)

        assert result is not None
        assert result.region.x == button_x
        assert result.region.y == button_y
        assert result.confidence > 0.99

    def test_returns_none_when_template_not_present(self, imaging: ImagingManager) -> None:
        """A smooth gradient background is self-similar almost everywhere, so a
        genuinely distinctive template (a drawn button, not a plain background
        crop) is required to prove "not present" actually means not present.
        """
        screen = _render_screen(imaging, seed=1)
        distinctive_template = _draw_button(
            _render_screen(imaging, seed=2), 10, 10, 60, 60, "X"
        ).crop(10, 10, 60, 60)

        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(screen, distinctive_template, confidence=0.9)

        assert result is None

    def test_tap_center_lands_inside_the_button(self, imaging: ImagingManager) -> None:
        """The coordinate a caller would tap must actually fall within the drawn button."""
        screen = _render_screen(imaging, seed=3)
        button_x, button_y, button_w, button_h = 100, 250, 120, 50
        screen = _draw_button(screen, button_x, button_y, button_w, button_h, "OK")
        template = screen.crop(button_x, button_y, button_w, button_h)

        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(screen, template, confidence=0.9)

        assert result is not None
        cx, cy = result.center
        assert button_x <= cx <= button_x + button_w
        assert button_y <= cy <= button_y + button_h


class TestRobustness:
    def test_still_found_under_mild_gaussian_noise(self, imaging: ImagingManager) -> None:
        """A live device capture is never pixel-identical run to run; the matcher must
        tolerate the sensor/encode noise a real screenshot would have.
        """
        screen = _render_screen(imaging, seed=4)
        button_x, button_y, button_w, button_h = 400, 100, 140, 55
        screen = _draw_button(screen, button_x, button_y, button_w, button_h, "GO")
        template = screen.crop(button_x, button_y, button_w, button_h)

        rng = numpy.random.default_rng(99)
        noisy_data = screen.data.astype(numpy.int16)
        noisy_data += rng.integers(-8, 8, size=noisy_data.shape)
        noisy_screen = Image(numpy.clip(noisy_data, 0, 255).astype(numpy.uint8), imaging.backend)

        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(noisy_screen, template, confidence=0.8)

        assert result is not None
        assert abs(result.region.x - button_x) <= 2
        assert abs(result.region.y - button_y) <= 2

    def test_high_confidence_threshold_rejects_dissimilar_region(
        self, imaging: ImagingManager
    ) -> None:
        screen = _render_screen(imaging, seed=5)
        button_x, button_y, button_w, button_h = 250, 300, 130, 50
        screen = _draw_button(screen, button_x, button_y, button_w, button_h, "NEXT")
        template = screen.crop(button_x, button_y, button_w, button_h)

        # Corrupt the template so it no longer matches anything on screen well.
        corrupted = template.data.copy()
        corrupted[:, :] = 255 - corrupted[:, :]
        corrupted_template = Image(corrupted, imaging.backend)

        matcher = TemplateMatcher(imaging)
        result = matcher.find_best(screen, corrupted_template, confidence=0.95)
        assert result is None


class TestMultipleElements:
    def test_finds_each_distinct_button_independently(self, imaging: ImagingManager) -> None:
        screen = _render_screen(imaging, seed=6)
        screen = _draw_button(screen, 50, 50, 100, 40, "A")
        screen = _draw_button(screen, 400, 300, 100, 40, "B")

        template_a = screen.crop(50, 50, 100, 40)
        template_b = screen.crop(400, 300, 100, 40)

        matcher = TemplateMatcher(imaging)
        result_a = matcher.find_best(screen, template_a, confidence=0.9)
        result_b = matcher.find_best(screen, template_b, confidence=0.9)

        assert result_a is not None and (result_a.region.x, result_a.region.y) == (50, 50)
        assert result_b is not None and (result_b.region.x, result_b.region.y) == (400, 300)

    def test_find_all_does_not_duplicate_a_single_button(self, imaging: ImagingManager) -> None:
        screen = _render_screen(imaging, seed=7)
        screen = _draw_button(screen, 200, 200, 100, 40, "ONE")
        template = screen.crop(200, 200, 100, 40)

        matcher = TemplateMatcher(imaging)
        results = matcher.find_all(screen, template, confidence=0.9)

        assert len(results) == 1
