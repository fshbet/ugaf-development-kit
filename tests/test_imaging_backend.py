"""Tests for the ImageBackend ABC."""

from __future__ import annotations

import pytest

from ugaf.imaging.backend import ImageBackend


class TestImageBackend:
    def test_abstract_cannot_instantiate(self) -> None:
        with pytest.raises(TypeError):
            ImageBackend()  # type: ignore[abstract]
