"""Provider registry for the input engine plugin system."""

from __future__ import annotations

import threading
from typing import Any

from ugaf.input.provider import InputProvider

__all__ = [
    "InputProviderRegistry",
    "registry",
]


class InputProviderRegistry:
    """Thread-safe registry for named :class:`InputProvider` classes.

    Supports dynamic registration, unregistration, and factory-style
    instantiation.  Used by :class:`~ugaf.input.manager.InputManager`
    to select and create providers without hard-coding concrete types.
    """

    def __init__(self) -> None:
        self._providers: dict[str, type[InputProvider]] = {}
        self._lock = threading.Lock()

    def register(self, name: str, provider_cls: type[InputProvider]) -> None:
        """Register an input provider class under *name*.

        Args:
            name: Short identifier (e.g. ``"windows"``, ``"adb"``).
            provider_cls: Concrete :class:`InputProvider` subclass.

        Raises:
            TypeError: If *provider_cls* is not an
                :class:`InputProvider` subclass.
            ValueError: If *name* is already registered.

        """
        if not (isinstance(provider_cls, type) and issubclass(provider_cls, InputProvider)):
            raise TypeError(
                f"{provider_cls!r} is not an InputProvider subclass"
            )
        with self._lock:
            if name in self._providers:
                raise ValueError(f"Provider {name!r} is already registered")
            self._providers[name] = provider_cls

    def unregister(self, name: str) -> None:
        """Remove a previously registered provider.

        Args:
            name: The provider identifier.

        Raises:
            KeyError: If *name* is not registered.

        """
        with self._lock:
            self._providers.pop(name)

    def create(
        self,
        name: str,
        config: dict[str, Any] | None = None,
    ) -> InputProvider:
        """Create an instance of the named provider.

        Args:
            name: The provider identifier.
            config: Optional configuration dict forwarded to the
                provider's constructor.

        Returns:
            A new :class:`InputProvider` instance.

        Raises:
            KeyError: If *name* is not registered.

        """
        with self._lock:
            provider_cls = self._providers[name]
        return provider_cls(config or {})

    def list_providers(self) -> list[str]:
        """Return sorted list of registered provider names."""
        with self._lock:
            return sorted(self._providers)

    def is_registered(self, name: str) -> bool:
        """Return whether *name* is registered."""
        with self._lock:
            return name in self._providers


# Module-level singleton — shared across the framework.
registry = InputProviderRegistry()
