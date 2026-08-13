"""AVD name sanitization: user-entered display names vs. ``avdmanager`` identifiers.

``avdmanager create avd -n <name>`` rejects (or silently mangles) names
containing spaces or most punctuation -- it only reliably accepts
letters, digits, underscores, hyphens, and periods. Previously, a
display name like ``"ROG A15"`` typed into the web UI was passed
straight through to ``avdmanager``, which is exactly the kind of SDK
implementation detail a user should never need to know about or work
around themselves.
"""

from __future__ import annotations

import re

__all__ = [
    "sanitize_avd_name",
]

_VALID_CHARS = re.compile(r"[^A-Za-z0-9_.-]")
_COLLAPSE_UNDERSCORES = re.compile(r"_+")


def sanitize_avd_name(name: str) -> str:
    """Convert a free-form display name into a valid ``avdmanager`` identifier.

    Whitespace and any character outside ``avdmanager``'s accepted set
    (letters, digits, underscore, hyphen, period) become underscores;
    runs of underscores collapse to one, and leading/trailing
    underscores are stripped.

    Args:
        name: The user-entered display name (e.g. ``"ROG A15"``).

    Returns:
        A sanitized identifier safe to pass to ``avdmanager``
        (e.g. ``"ROG_A15"``).

    Raises:
        ValueError: If *name* sanitizes to an empty string (e.g. it
            was blank or made up entirely of unsupported characters).

    """
    sanitized = _VALID_CHARS.sub("_", name.strip())
    sanitized = _COLLAPSE_UNDERSCORES.sub("_", sanitized).strip("_")
    if not sanitized:
        raise ValueError(
            f"{name!r} cannot be turned into a valid Android Virtual Device name "
            "-- use at least one letter, digit, hyphen, or period."
        )
    return sanitized
