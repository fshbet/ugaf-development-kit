"""Base exception hierarchy for the UGAF framework."""

from __future__ import annotations


class UGAFError(Exception):
    """Base exception for all UGAF framework errors.

    All custom exceptions in the framework inherit from this class so
    that callers can catch a single base type if desired.

    """


class ConfigError(UGAFError):
    """Raised when configuration loading or validation fails."""


class EventBusError(UGAFError):
    """Raised when an event bus operation fails."""


class PluginLoaderError(UGAFError):
    """Raised when plugin discovery or loading fails."""


class ApplicationError(UGAFError, RuntimeError):
    """Raised when the application lifecycle is used incorrectly.

    Inherits from both ``UGAFError`` and ``RuntimeError`` so that
    existing callers catching ``RuntimeError`` still work.

    """
