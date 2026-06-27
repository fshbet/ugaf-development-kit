"""Manifest validation for UGAF game plugins."""

from __future__ import annotations

import re
from typing import Any

from ugaf.sdk.capabilities import Capability
from ugaf.sdk.exceptions import PluginValidationError
from ugaf.sdk.metadata import PluginMetadata

__all__ = [
    "PluginValidator",
]

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_REQUIRED_FIELDS = ("name", "id", "author", "version")
_FRAMEWORK_VERSION = "1.0.0"


class PluginValidator:
    """Validates plugin manifests and produces :class:`PluginMetadata`.

    Usage::

        metadata = PluginValidator.validate_manifest(raw_yaml_dict)

    """

    @staticmethod
    def validate_manifest(data: dict[str, Any]) -> PluginMetadata:
        """Validate a raw manifest dict and return structured metadata.

        Args:
            data: Raw dictionary parsed from ``manifest.yaml``.

        Returns:
            Populated :class:`PluginMetadata`.

        Raises:
            PluginValidationError: If any validation check fails.

        """
        for field in _REQUIRED_FIELDS:
            value = data.get(field)
            if not value or not isinstance(value, str) or not value.strip():
                raise PluginValidationError(f"Manifest is missing required field: {field!r}")

        name = str(data["name"]).strip()
        plugin_id = str(data["id"]).strip()
        author = str(data["author"]).strip()
        version = str(data["version"]).strip()
        description = str(data.get("description", "") or "").strip()
        min_fw = str(data.get("minimum_framework_version", "1.0.0") or "").strip()

        if not _SEMVER_RE.match(version):
            raise PluginValidationError(
                f"Invalid version format: {version!r} (expected semver like 1.0.0)"
            )

        if not _SEMVER_RE.match(min_fw):
            raise PluginValidationError(f"Invalid minimum_framework_version: {min_fw!r}")

        _check_framework_compatibility(min_fw)

        capabilities: list[Capability] = []
        raw_caps = data.get("capabilities", [])
        if not isinstance(raw_caps, list):
            raise PluginValidationError("capabilities must be a list")
        for cap in raw_caps:
            try:
                capabilities.append(Capability(str(cap)))
            except ValueError:
                raise PluginValidationError(f"Unknown capability: {cap!r}")

        supported_platforms: list[str] = [
            str(p).strip()
            for p in data.get("supported_platforms", [])
            if isinstance(p, str) and p.strip()
        ]

        priority = 100
        raw_priority = data.get("priority", 100)
        if isinstance(raw_priority, int):
            priority = raw_priority

        return PluginMetadata(
            name=name,
            id=plugin_id,
            author=author,
            version=version,
            description=description,
            supported_platforms=supported_platforms,
            minimum_framework_version=min_fw,
            capabilities=capabilities,
            priority=priority,
        )


def _check_framework_compatibility(min_fw: str) -> None:
    """Compare *min_fw* against the current framework version.

    Raises:
        PluginValidationError: If the framework is too old.

    """
    min_parts = _parse_version(min_fw)
    current_parts = _parse_version(_FRAMEWORK_VERSION)
    if min_parts > current_parts:
        raise PluginValidationError(
            f"Plugin requires framework version {min_fw} "
            f"but current version is {_FRAMEWORK_VERSION}"
        )


def _parse_version(version: str) -> tuple[int, int, int]:
    """Parse a semver string into a comparable tuple."""
    parts = version.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))
