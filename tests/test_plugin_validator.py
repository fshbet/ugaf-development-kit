"""Tests for the PluginValidator manifest validation."""

from __future__ import annotations

import pytest

from ugaf.plugins.validator import PluginValidator
from ugaf.sdk.capabilities import Capability
from ugaf.sdk.exceptions import PluginValidationError

_VALID_MANIFEST = {
    "name": "Test Game",
    "id": "test_game",
    "author": "Test Author",
    "version": "1.0.0",
    "description": "A test plugin",
    "supported_platforms": ["windows"],
    "minimum_framework_version": "1.0.0",
    "capabilities": ["input"],
    "priority": 100,
}


class TestPluginValidator:
    def test_valid_manifest(self) -> None:
        meta = PluginValidator.validate_manifest(dict(_VALID_MANIFEST))
        assert meta.name == "Test Game"
        assert meta.id == "test_game"
        assert meta.author == "Test Author"
        assert meta.version == "1.0.0"
        assert meta.description == "A test plugin"
        assert meta.supported_platforms == ["windows"]
        assert meta.capabilities == [Capability.INPUT]
        assert meta.priority == 100

    def test_minimal_valid(self) -> None:
        meta = PluginValidator.validate_manifest(
            {
                "name": "Minimal",
                "id": "minimal",
                "author": "Tester",
                "version": "0.1.0",
            }
        )
        assert meta.name == "Minimal"
        assert meta.description == ""
        assert meta.capabilities == []
        assert meta.priority == 100

    # ------------------------------------------------------------------
    # Required fields
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("field", ["name", "id", "author", "version"])
    def test_missing_required_field(self, field: str) -> None:
        data = dict(_VALID_MANIFEST)
        del data[field]
        with pytest.raises(PluginValidationError, match="missing required field"):
            PluginValidator.validate_manifest(data)

    @pytest.mark.parametrize("field", ["name", "id", "author", "version"])
    def test_empty_required_field(self, field: str) -> None:
        data = dict(_VALID_MANIFEST)
        data[field] = ""
        with pytest.raises(PluginValidationError, match="missing required field"):
            PluginValidator.validate_manifest(data)

    @pytest.mark.parametrize("field", ["name", "id", "author", "version"])
    def test_whitespace_required_field(self, field: str) -> None:
        data = dict(_VALID_MANIFEST)
        data[field] = "   "
        with pytest.raises(PluginValidationError, match="missing required field"):
            PluginValidator.validate_manifest(data)

    def test_non_string_required_field(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["name"] = 123
        with pytest.raises(PluginValidationError, match="missing required field"):
            PluginValidator.validate_manifest(data)

    # ------------------------------------------------------------------
    # Version validation
    # ------------------------------------------------------------------

    @pytest.mark.parametrize(
        "bad_version", ["1.0", "1", "a.b.c", "1.0.0.0", "v1.0.0", "1.0.0-beta"]
    )
    def test_invalid_semver(self, bad_version: str) -> None:
        data = dict(_VALID_MANIFEST)
        data["version"] = bad_version
        with pytest.raises(PluginValidationError, match="Invalid version"):
            PluginValidator.validate_manifest(data)

    def test_invalid_minimum_framework_version(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["minimum_framework_version"] = "abc"
        with pytest.raises(PluginValidationError, match="Invalid minimum_framework_version"):
            PluginValidator.validate_manifest(data)

    def test_framework_too_old(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["minimum_framework_version"] = "99.0.0"
        with pytest.raises(PluginValidationError, match="requires framework version"):
            PluginValidator.validate_manifest(data)

    # ------------------------------------------------------------------
    # Capabilities
    # ------------------------------------------------------------------

    def test_invalid_capability(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["capabilities"] = ["unknown_cap"]
        with pytest.raises(PluginValidationError, match="Unknown capability"):
            PluginValidator.validate_manifest(data)

    def test_capabilities_not_a_list(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["capabilities"] = "input"
        with pytest.raises(PluginValidationError, match="capabilities must be a list"):
            PluginValidator.validate_manifest(data)

    def test_empty_capabilities(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["capabilities"] = []
        meta = PluginValidator.validate_manifest(data)
        assert meta.capabilities == []

    # ------------------------------------------------------------------
    # Priority
    # ------------------------------------------------------------------

    def test_custom_priority(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["priority"] = 50
        meta = PluginValidator.validate_manifest(data)
        assert meta.priority == 50

    def test_priority_default_when_missing(self) -> None:
        data = dict(_VALID_MANIFEST)
        del data["priority"]
        meta = PluginValidator.validate_manifest(data)
        assert meta.priority == 100

    def test_priority_negative_raises(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["priority"] = -1
        with pytest.raises(PluginValidationError, match="priority must be between"):
            PluginValidator.validate_manifest(data)

    def test_priority_too_high_raises(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["priority"] = 1001
        with pytest.raises(PluginValidationError, match="priority must be between"):
            PluginValidator.validate_manifest(data)

    # ------------------------------------------------------------------
    # Supported platforms
    # ------------------------------------------------------------------

    def test_supported_platforms_empty(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["supported_platforms"] = []
        meta = PluginValidator.validate_manifest(data)
        assert meta.supported_platforms == []

    def test_supported_platforms_filters_blanks(self) -> None:
        data = dict(_VALID_MANIFEST)
        data["supported_platforms"] = ["windows", "", "linux"]
        meta = PluginValidator.validate_manifest(data)
        assert meta.supported_platforms == ["windows", "linux"]
