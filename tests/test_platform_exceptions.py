"""Tests for the Platform Abstraction Layer exception hierarchy."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError
from ugaf.platform.exceptions import (
    AdapterNotAvailableError,
    AdapterNotConnectedError,
    PlatformLayerError,
)


def test_platform_layer_error_is_ugaf_error() -> None:
    assert issubclass(PlatformLayerError, UGAFError)


def test_adapter_not_available_is_platform_layer_error() -> None:
    assert issubclass(AdapterNotAvailableError, PlatformLayerError)


def test_adapter_not_connected_is_platform_layer_error() -> None:
    assert issubclass(AdapterNotConnectedError, PlatformLayerError)


def test_can_raise_and_catch_as_base() -> None:
    try:
        raise AdapterNotAvailableError("boom")
    except PlatformLayerError as exc:
        assert str(exc) == "boom"
