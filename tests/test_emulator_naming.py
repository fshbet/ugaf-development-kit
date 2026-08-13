"""Tests for ugaf.emulator.naming.sanitize_avd_name."""

from __future__ import annotations

import pytest

from ugaf.emulator.naming import sanitize_avd_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ROG A15", "ROG_A15"),
        ("My Pixel 9!", "My_Pixel_9"),
        ("already_valid-1.0", "already_valid-1.0"),
        ("  leading and trailing  ", "leading_and_trailing"),
        ("multiple   spaces", "multiple_spaces"),
        ("emoji😀name", "emoji_name"),
    ],
)
def test_sanitize_avd_name(raw: str, expected: str) -> None:
    assert sanitize_avd_name(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "!!!", "😀😀😀"])
def test_sanitize_avd_name_rejects_names_with_no_valid_characters(raw: str) -> None:
    with pytest.raises(ValueError, match="cannot be turned into a valid"):
        sanitize_avd_name(raw)
