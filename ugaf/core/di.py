"""Dependency Injection container for the UGAF framework."""

from __future__ import annotations

import inspect
import threading
from collections.abc import Callable
from enum import Enum
from typing import Any

from ugaf.core.exceptions import CircularDependencyError, DependencyInjectionError

__all__ = [
    "DependencyContainer",
    "ServiceLifetime",
]


class ServiceLifetime(Enum):
    """Lifetime options for registered services.

    Attributes:
        SINGLETON: A single instance shared across all resolutions.
        TRANSIENT: A new instance created for each resolution.

    """

    SINGLETON = "singleton"
    TRANSIENT = "transient"


class _ServiceDescriptor:
    """Internal descriptor for a registered service."""

    def __init__(
        self,
        lifetime: ServiceLifetime,
        implementation: type | Callable[..., Any] | None = None,
        instance: Any = None,
    ) -> None:
        self.lifetime = lifetime
        self.implementation = implementation
        self.instance = instance


class DependencyContainer:
    """Lightweight dependency injection container.

    Supports singleton and transient lifetimes with automatic
    constructor injection and circular dependency detection.

    Thread-safe for concurrent resolutions.

    Usage::

        container = DependencyContainer()

        class Database:
            ...

        class Service:
            def __init__(self, db: Database) -> None:
                self.db = db

        container.register_singleton(Database)
        container.register_transient(Service, Service)

        service = container.resolve(Service)
    """

    def __init__(self) -> None:
        """Initialize the container with an empty service registry."""
        self._services: dict[str, _ServiceDescriptor] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_singleton(
        self,
        interface: type,
        implementation: type | Callable[..., Any] | Any = None,
    ) -> None:
        """Register a service as a singleton.

        When *implementation* is omitted, *interface* is used as both
        the key and the concrete type. When *implementation* is a
        concrete instance, it is stored directly.

        Args:
            interface: The abstract or concrete type to register.
            implementation: The concrete implementation type, a factory
                callable, or a pre-built instance. If ``None``, uses
                *interface* itself.

        Raises:
            DependencyInjectionError: If the interface is already
                registered.

        """
        key = self._key(interface)
        with self._lock:
            if key in self._services:
                raise DependencyInjectionError(
                    f"Service {interface.__name__} is already registered"
                )
            if not callable(implementation) and implementation is not None:
                self._services[key] = _ServiceDescriptor(
                    lifetime=ServiceLifetime.SINGLETON,
                    instance=implementation,
                )
            else:
                self._services[key] = _ServiceDescriptor(
                    lifetime=ServiceLifetime.SINGLETON,
                    implementation=implementation or interface,
                )

    def register_transient(
        self,
        interface: type,
        implementation: type,
    ) -> None:
        """Register a service as transient.

        A new instance is created on every ``resolve()`` call.

        Args:
            interface: The abstract or concrete type to register.
            implementation: The concrete implementation type.

        Raises:
            DependencyInjectionError: If the interface is already
                registered.

        """
        key = self._key(interface)
        with self._lock:
            if key in self._services:
                raise DependencyInjectionError(
                    f"Service {interface.__name__} is already registered"
                )
            self._services[key] = _ServiceDescriptor(
                lifetime=ServiceLifetime.TRANSIENT,
                implementation=implementation,
            )

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, interface: type) -> Any:
        """Resolve a service by its interface type.

        Automatically injects constructor dependencies for the
        concrete implementation type using type hints.

        Args:
            interface: The type to resolve.

        Returns:
            The resolved service instance.

        Raises:
            DependencyInjectionError: If the service is not registered.
            CircularDependencyError: If a circular dependency is
                detected.

        """
        key = self._key(interface)
        descriptor = self._services.get(key)
        if descriptor is None:
            raise DependencyInjectionError(f"Service {interface.__name__} is not registered")
        return self._resolve_descriptor(descriptor, set())

    def resolve_all(self, interface: type) -> list[Any]:
        """Resolve all services matching the given interface.

        Uses interface-based matching via ``isinstance`` check on
        registered implementations. Useful for resolving multiple
        implementations of the same protocol.

        Args:
            interface: The base type or protocol to match.

        Returns:
            A list of resolved service instances that match the
            interface.

        """
        results: list[Any] = []
        with self._lock:
            descriptors = list(self._services.values())
        for descriptor in descriptors:
            impl = descriptor.implementation
            if impl is not None and isinstance(impl, type) and issubclass(impl, interface):
                results.append(self._resolve_descriptor(descriptor, set()))
        return results

    # ------------------------------------------------------------------
    # Registration queries
    # ------------------------------------------------------------------

    def is_registered(self, interface: type) -> bool:
        """Check whether a service is registered.

        Args:
            interface: The type to check.

        Returns:
            ``True`` if the service is registered.

        """
        return self._key(interface) in self._services

    def clear(self) -> None:
        """Remove all registered services and cached singletons."""
        with self._lock:
            self._services.clear()

    @property
    def count(self) -> int:
        """Return the number of registered services."""
        return len(self._services)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_descriptor(
        self,
        descriptor: _ServiceDescriptor,
        visiting: set[str],
    ) -> Any:
        """Resolve a descriptor, building its dependency graph.

        Args:
            descriptor: The descriptor to resolve.
            visiting: Set of keys currently being resolved (for
                circular dependency detection).

        Returns:
            The resolved service instance.

        """
        if descriptor.lifetime is ServiceLifetime.SINGLETON:
            with self._lock:
                if descriptor.instance is not None:
                    return descriptor.instance

        impl = descriptor.implementation
        if impl is None:
            raise DependencyInjectionError("Service descriptor has no implementation")

        if isinstance(impl, type):
            instance = self._construct(impl, visiting)
        else:
            instance = impl()

        if descriptor.lifetime is ServiceLifetime.SINGLETON:
            with self._lock:
                descriptor.instance = instance

        return instance

    def _construct(self, cls: type, visiting: set[str]) -> Any:
        """Construct an instance of *cls* with injected dependencies.

        Args:
            cls: The class to instantiate.
            visiting: Set of dependency keys currently being resolved.

        Returns:
            A new instance of *cls*.

        """
        key = self._key(cls)
        if key in visiting:
            raise CircularDependencyError(
                f"Circular dependency detected while resolving {cls.__name__}"
            )
        visiting.add(key)

        try:
            sig = inspect.signature(cls)
            params = list(sig.parameters.values())[1:]  # skip self
            hints = self._get_type_hints(cls)

            kwargs: dict[str, Any] = {}
            for param in params:
                if param.annotation is inspect.Parameter.empty:
                    if param.default is inspect.Parameter.empty:
                        raise DependencyInjectionError(
                            f"Cannot inject parameter '{param.name}' in "
                            f"{cls.__name__}: missing type hint"
                        )
                    continue
                if param.default is not inspect.Parameter.empty:
                    continue
                dep_type = hints.get(param.name)
                if dep_type is None:
                    continue
                kwargs[param.name] = self._resolve_dependency(dep_type, visiting)

            instance = cls(**kwargs)
        finally:
            visiting.discard(key)

        return instance

    def _resolve_dependency(self, dep_type: type, visiting: set[str]) -> Any:
        """Resolve a single dependency by its declared type.

        Args:
            dep_type: The type to resolve.
            visiting: Set of keys currently being resolved.

        Returns:
            The resolved dependency.

        """
        key = self._key(dep_type)
        descriptor = self._services.get(key)
        if descriptor is not None:
            return self._resolve_descriptor(descriptor, visiting)
        raise DependencyInjectionError(
            f"Unregistered dependency {dep_type.__name__} " f"required by constructor"
        )

    def _get_type_hints(self, cls: type) -> dict[str, type]:
        """Retrieve constructor type hints for a class.

        Args:
            cls: The class to inspect.

        Returns:
            Dictionary of parameter name to type.

        """
        try:
            hints = inspect.get_annotations(cls)
        except OSError:
            return {}
        if "return" in hints:
            del hints["return"]
        return hints

    @staticmethod
    def _key(interface: type) -> str:
        """Generate a registry key for an interface type."""
        return f"{interface.__module__}.{interface.__qualname__}"
