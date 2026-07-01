"""Generic, thread-safe adapter registry for the Platform Abstraction Layer.

Generalizes the pattern already proven by
:class:`ugaf.input.registry.InputProviderRegistry`: each platform
subsystem (display, clipboard, file system, ...) owns one
:class:`AdapterRegistry` instance parametrized with its own base
interface type, so adapter registration/selection code is written
once instead of once per subsystem.
"""

from __future__ import annotations

import threading
from typing import Any

__all__ = [
    "AdapterRegistry",
]


class AdapterRegistry[T]:
    """Thread-safe registry of named adapter classes for a single interface.

    Usage::

        registry: AdapterRegistry[ClipboardProvider] = AdapterRegistry(ClipboardProvider)
        registry.register("windows", WindowsClipboardProvider)
        clipboard = registry.create("windows")
    """

    def __init__(self, interface: type[T]) -> None:
        """Initialize an empty registry bound to a base interface type.

        Args:
            interface: The abstract base class every registered
                adapter must subclass. Enforced at registration time.

        """
        self._interface = interface
        self._adapters: dict[str, type[T]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, adapter_cls: type[T]) -> None:
        """Register an adapter class under *name*.

        Args:
            name: Short identifier (e.g. ``"windows"``, ``"android"``).
            adapter_cls: Concrete subclass of this registry's interface.

        Raises:
            TypeError: If *adapter_cls* is not a subclass of the
                registry's bound interface.
            ValueError: If *name* is already registered.

        """
        if not (isinstance(adapter_cls, type) and issubclass(adapter_cls, self._interface)):
            raise TypeError(f"{adapter_cls!r} is not a subclass of {self._interface.__name__}")
        with self._lock:
            if name in self._adapters:
                raise ValueError(f"Adapter {name!r} is already registered")
            self._adapters[name] = adapter_cls

    def unregister(self, name: str) -> None:
        """Remove a previously registered adapter.

        Args:
            name: The adapter identifier.

        Raises:
            KeyError: If *name* is not registered.

        """
        with self._lock:
            self._adapters.pop(name)

    def create(self, name: str, *args: Any, **kwargs: Any) -> T:
        """Instantiate the named adapter.

        Args:
            name: The adapter identifier.
            *args: Positional arguments forwarded to the constructor.
            **kwargs: Keyword arguments forwarded to the constructor.

        Returns:
            A new adapter instance.

        Raises:
            KeyError: If *name* is not registered.

        """
        with self._lock:
            adapter_cls = self._adapters[name]
        return adapter_cls(*args, **kwargs)

    def list_adapters(self) -> list[str]:
        """Return the sorted list of registered adapter names."""
        with self._lock:
            return sorted(self._adapters)

    def is_registered(self, name: str) -> bool:
        """Return whether *name* is registered."""
        with self._lock:
            return name in self._adapters
