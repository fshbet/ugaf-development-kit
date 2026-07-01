"""Tests for the generic AdapterRegistry."""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod

import pytest

from ugaf.platform.registry import AdapterRegistry


class _Interface(ABC):
    @abstractmethod
    def ping(self) -> str: ...


class _AdapterA(_Interface):
    def ping(self) -> str:
        return "a"


class _AdapterB(_Interface):
    def __init__(self, tag: str = "b") -> None:
        self.tag = tag

    def ping(self) -> str:
        return self.tag


class _NotAnAdapter:
    pass


def test_register_and_create() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    reg.register("a", _AdapterA)
    instance = reg.create("a")
    assert isinstance(instance, _AdapterA)
    assert instance.ping() == "a"


def test_create_forwards_args() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    reg.register("b", _AdapterB)
    instance = reg.create("b", tag="custom")
    assert isinstance(instance, _AdapterB)
    assert instance.ping() == "custom"


def test_register_rejects_non_subclass() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    with pytest.raises(TypeError, match="not a subclass"):
        reg.register("bad", _NotAnAdapter)  # type: ignore[arg-type]


def test_register_duplicate_raises() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    reg.register("a", _AdapterA)
    with pytest.raises(ValueError, match="already registered"):
        reg.register("a", _AdapterA)


def test_unregister() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    reg.register("a", _AdapterA)
    reg.unregister("a")
    assert reg.is_registered("a") is False


def test_unregister_missing_raises() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    with pytest.raises(KeyError):
        reg.unregister("missing")


def test_create_missing_raises() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    with pytest.raises(KeyError):
        reg.create("missing")


def test_list_adapters_sorted() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    reg.register("b", _AdapterB)
    reg.register("a", _AdapterA)
    assert reg.list_adapters() == ["a", "b"]


def test_is_registered() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    assert reg.is_registered("a") is False
    reg.register("a", _AdapterA)
    assert reg.is_registered("a") is True


def test_concurrent_registration_is_thread_safe() -> None:
    reg: AdapterRegistry[_Interface] = AdapterRegistry(_Interface)
    errors: list[Exception] = []

    def _register(name: str) -> None:
        try:
            reg.register(name, _AdapterA)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_register, args=(f"adapter-{i}",)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(reg.list_adapters()) == 20
