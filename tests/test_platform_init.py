"""Tests for the ugaf.platform package's default adapter registrations."""

from __future__ import annotations

import ugaf.platform as platform_pkg


def test_clipboard_registry_has_windows_adapter() -> None:
    assert platform_pkg.clipboard_registry.is_registered("windows")


def test_display_registry_has_windows_adapter() -> None:
    assert platform_pkg.display_registry.is_registered("windows")


def test_notification_registry_has_windows_adapter() -> None:
    assert platform_pkg.notification_registry.is_registered("windows")


def test_filesystem_registry_has_local_adapter() -> None:
    assert platform_pkg.filesystem_registry.is_registered("local")


def test_network_registry_has_default_adapter() -> None:
    assert platform_pkg.network_registry.is_registered("default")


def test_process_registry_has_default_adapter() -> None:
    assert platform_pkg.process_registry.is_registered("default")


def test_device_and_accessibility_registries_start_empty() -> None:
    """No concrete adapters ship in Milestone 2 for these two subsystems."""
    assert platform_pkg.device_registry.list_adapters() == []
    assert platform_pkg.accessibility_registry.list_adapters() == []
