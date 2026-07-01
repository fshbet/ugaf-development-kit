"""Tests for MockScreenshotProvider and ImageReplayProvider."""

from __future__ import annotations

from pathlib import Path

import numpy
import pytest

from ugaf.imaging.image import Image
from ugaf.imaging.manager import ImagingManager
from ugaf.vision.exceptions import ScreenshotError
from ugaf.vision.mock_screenshot import ImageReplayProvider, MockScreenshotProvider
from ugaf.vision.region import Region


@pytest.fixture
def imaging() -> ImagingManager:
    return ImagingManager()


class TestMockScreenshotProvider:
    def test_capture_full_generates_solid_color_image(self, imaging: ImagingManager) -> None:
        provider = MockScreenshotProvider(imaging, width=320, height=240, color=(1, 2, 3))
        img = provider.capture_full()
        assert img.size.width == 320
        assert img.size.height == 240
        assert tuple(img.data[0, 0]) == (1, 2, 3)

    def test_capture_full_returns_static_image_when_given(self, imaging: ImagingManager) -> None:
        static = Image(numpy.zeros((10, 10, 3), dtype=numpy.uint8), imaging.backend)
        provider = MockScreenshotProvider(imaging, static_image=static)
        assert provider.capture_full() is static

    def test_capture_region_crops(self, imaging: ImagingManager) -> None:
        provider = MockScreenshotProvider(imaging, width=100, height=100)
        region = Region(10, 10, 20, 20)
        cropped = provider.capture_region(region)
        assert cropped.size.width == 20
        assert cropped.size.height == 20

    def test_capture_game_window_returns_same_synthetic_image(
        self, imaging: ImagingManager
    ) -> None:
        provider = MockScreenshotProvider(imaging, width=50, height=50)
        img = provider.capture_game_window("anything")
        assert img.size.width == 50


class TestImageReplayProvider:
    def test_requires_paths_or_directory(self, imaging: ImagingManager) -> None:
        with pytest.raises(ValueError, match="paths or directory"):
            ImageReplayProvider(imaging)

    def test_raises_if_no_images_found(self, imaging: ImagingManager, tmp_path: Path) -> None:
        with pytest.raises(ScreenshotError, match="no images"):
            ImageReplayProvider(imaging, directory=tmp_path)

    def test_cycles_through_explicit_paths(self, imaging: ImagingManager, tmp_path: Path) -> None:
        img_a = tmp_path / "a.png"
        img_b = tmp_path / "b.png"
        Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(img_a)
        Image(numpy.full((6, 6, 3), 9, dtype=numpy.uint8), imaging.backend).save(img_b)

        provider = ImageReplayProvider(imaging, paths=[img_a, img_b])
        first = provider.capture_full()
        second = provider.capture_full()
        assert first.size.width == 5
        assert second.size.width == 6

    def test_loops_back_to_start_when_loop_true(
        self, imaging: ImagingManager, tmp_path: Path
    ) -> None:
        img_a = tmp_path / "a.png"
        Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(img_a)
        provider = ImageReplayProvider(imaging, paths=[img_a], loop=True)

        provider.capture_full()
        second = provider.capture_full()  # wraps back to the same single image
        assert second.size.width == 5

    def test_raises_when_exhausted_and_loop_false(
        self, imaging: ImagingManager, tmp_path: Path
    ) -> None:
        img_a = tmp_path / "a.png"
        Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(img_a)
        provider = ImageReplayProvider(imaging, paths=[img_a], loop=False)

        provider.capture_full()
        with pytest.raises(ScreenshotError, match="exhausted"):
            provider.capture_full()

    def test_remaining_counts_down(self, imaging: ImagingManager, tmp_path: Path) -> None:
        img_a = tmp_path / "a.png"
        img_b = tmp_path / "b.png"
        Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(img_a)
        Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(img_b)
        provider = ImageReplayProvider(imaging, paths=[img_a, img_b], loop=False)

        assert provider.remaining == 2
        provider.capture_full()
        assert provider.remaining == 1
        provider.capture_full()
        assert provider.remaining == 0

    def test_directory_scans_sorted_image_files(
        self, imaging: ImagingManager, tmp_path: Path
    ) -> None:
        for name in ("z.png", "a.png", "not_an_image.txt"):
            path = tmp_path / name
            if name.endswith(".png"):
                Image(numpy.zeros((5, 5, 3), dtype=numpy.uint8), imaging.backend).save(path)
            else:
                path.write_text("ignore me")

        provider = ImageReplayProvider(imaging, directory=tmp_path)
        assert [p.name for p in provider._paths] == ["a.png", "z.png"]

    def test_capture_region_and_window_delegate_to_capture_full(
        self, imaging: ImagingManager, tmp_path: Path
    ) -> None:
        img_a = tmp_path / "a.png"
        Image(numpy.zeros((10, 10, 3), dtype=numpy.uint8), imaging.backend).save(img_a)
        provider = ImageReplayProvider(imaging, paths=[img_a, img_a])

        region_result = provider.capture_region(Region(0, 0, 5, 5))
        assert region_result.size.width == 5

        window_result = provider.capture_game_window("any")
        assert window_result.size.width == 10
