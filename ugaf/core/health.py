"""Health check framework for the UGAF framework."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ugaf.core.exceptions import HealthCheckError

__all__ = [
    "HealthCheckable",
    "HealthRegistry",
    "HealthResult",
    "HealthStatus",
]


class HealthStatus(Enum):
    """Health status levels.

    Attributes:
        HEALTHY: Component is operating normally.
        WARNING: Component is degraded but functional.
        ERROR: Component has failed.

    """

    HEALTHY = "healthy"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class HealthResult:
    """Result of a single health check.

    Attributes:
        status: Health status level.
        component: Name of the checked component.
        message: Human-readable description.
        timestamp: Unix timestamp of when the check was performed.
        details: Additional structured data from the check.

    """

    status: HealthStatus
    component: str
    message: str = ""
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)


HealthCheckable = Callable[[], Awaitable[HealthResult]]
"""Type alias for an async health check callable."""


class HealthRegistry:
    """Registry for component health checks.

    Usage::

        registry = HealthRegistry()

        async def check_db() -> HealthResult:
            ...

        registry.register("database", check_db)
        results = await registry.run_all()
    """

    def __init__(self) -> None:
        """Initialize the registry with no checks registered."""
        self._checks: dict[str, HealthCheckable] = {}

    def register(self, name: str, check: HealthCheckable) -> None:
        """Register a health check by component name.

        Args:
            name: Component name (e.g. ``"database"``, ``"event_bus"``).
            check: Async callable that returns a ``HealthResult``.

        Raises:
            HealthCheckError: If the name is already registered.

        """
        if name in self._checks:
            raise HealthCheckError(f"Health check {name!r} is already registered")
        self._checks[name] = check

    def unregister(self, name: str) -> None:
        """Remove a registered health check.

        Args:
            name: Component name to remove.

        """
        self._checks.pop(name, None)

    async def run_all(self) -> list[HealthResult]:
        """Run all registered health checks concurrently.

        A check that raises an exception produces an ``ERROR`` result
        rather than propagating the exception.

        Returns:
            List of ``HealthResult`` for every registered check.

        """
        results: list[HealthResult] = []

        for name, check in list(self._checks.items()):
            try:
                result = await check()
                results.append(result)
            except Exception as exc:
                results.append(
                    HealthResult(
                        status=HealthStatus.ERROR,
                        component=name,
                        message=str(exc),
                    )
                )

        return results

    async def run_one(self, name: str) -> HealthResult | None:
        """Run a single health check by name.

        Args:
            name: Component name.

        Returns:
            The ``HealthResult``, or ``None`` if not registered.

        """
        check = self._checks.get(name)
        if check is None:
            return None
        try:
            return await check()
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.ERROR,
                component=name,
                message=str(exc),
            )

    @property
    def count(self) -> int:
        """Return the number of registered checks."""
        return len(self._checks)
