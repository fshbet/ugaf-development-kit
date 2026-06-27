"""Tests for the input engine exception hierarchy."""

from __future__ import annotations

from ugaf.core.exceptions import UGAFError
from ugaf.input.exceptions import (
    ConnectionFailedError,
    CoordinateOutOfBoundsError,
    DeviceNotFoundError,
    InputError,
    ProviderNotAvailableError,
)


def test_input_error_is_ugaf_error() -> None:
    assert issubclass(InputError, UGAFError)


def test_device_not_found_is_input_error() -> None:
    assert issubclass(DeviceNotFoundError, InputError)


def test_provider_not_available_is_input_error() -> None:
    assert issubclass(ProviderNotAvailableError, InputError)


def test_connection_failed_is_input_error() -> None:
    assert issubclass(ConnectionFailedError, InputError)


def test_coordinate_out_of_bounds_is_input_error() -> None:
    assert issubclass(CoordinateOutOfBoundsError, InputError)


def test_device_not_found_message() -> None:
    exc = DeviceNotFoundError("No devices connected")
    assert str(exc) == "No devices connected"


def test_provider_not_available_message() -> None:
    exc = ProviderNotAvailableError("Unknown provider: xyz")
    assert str(exc) == "Unknown provider: xyz"


def test_connection_failed_message() -> None:
    exc = ConnectionFailedError("ADB not found")
    assert str(exc) == "ADB not found"


def test_coordinate_out_of_bounds_message() -> None:
    exc = CoordinateOutOfBoundsError("(9999, 0) out of bounds")
    assert str(exc) == "(9999, 0) out of bounds"
