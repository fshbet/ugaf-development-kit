"""Minimal reader/writer for AVD ``config.ini``/``.ini`` files.

These files are flat ``key=value`` pairs with no section headers (see
the real ``config.ini`` excerpt in ``ARCHITECTURE_DECISIONS.md``'s
Emulator Manager ADR), so :mod:`configparser` (which requires a
section) does not apply directly — a small dedicated parser is simpler
and more faithful than working around that mismatch.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "read_avd_config",
    "write_avd_config",
]


def read_avd_config(path: Path) -> dict[str, str]:
    """Parse a flat ``key=value`` AVD config file into an ordered dict."""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        data[key.strip()] = value.strip()
    return data


def write_avd_config(path: Path, data: dict[str, str]) -> None:
    """Write *data* back out as a flat ``key=value`` AVD config file."""
    lines = [f"{key}={value}" for key, value in data.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
