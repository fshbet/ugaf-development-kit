"""Tests for the InputProviderRegistry."""

from __future__ import annotations

import threading

import pytest

from ugaf.input.provider import InputProvider
from ugaf.input.registry import InputProviderRegistry
from ugaf.input.types import Button, Key


class _MinimalProvider(InputProvider):
    """Minimal InputProvider subclass for registry tests."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}

    def connect(self) -> None: ...
    def disconnect(self) -> None: ...
    def is_connected(self) -> bool:
        return False

    @property
    def screen_size(self) -> tuple[int, int]:
        return (0, 0)

    def click(self, x: int, y: int, button: Button = "left") -> None: ...
    def double_click(self, x: int, y: int) -> None: ...
    def right_click(self, x: int, y: int) -> None: ...
    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None: ...
    def drag(self, x1: int, y1: int, x2: int, y2: int, duration: float = 0.0) -> None: ...
    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> None: ...
    def key_down(self, key: Key) -> None: ...
    def key_up(self, key: Key) -> None: ...
    def press_key(self, key: Key) -> None: ...
    def type_text(self, text: str) -> None: ...
    def hotkey(self, *keys: Key) -> None: ...
    def wait(self, seconds: float) -> None: ...
    def take_screenshot(self, path: str | None = None) -> bytes | None:
        return None


# ---------------------------------------------------------------------------
# Tests: registration
# ---------------------------------------------------------------------------


class TestRegister:
    def test_register_and_is_registered(self) -> None:
        reg = InputProviderRegistry()
        reg.register("test", _MinimalProvider)
        assert reg.is_registered("test") is True
        assert reg.is_registered("nonexistent") is False

    def test_duplicate_raises(self) -> None:
        reg = InputProviderRegistry()
        reg.register("dup", _MinimalProvider)
        with pytest.raises(ValueError, match="already registered"):
            reg.register("dup", _MinimalProvider)

    def test_register_invalid_type(self) -> None:
        reg = InputProviderRegistry()
        with pytest.raises(TypeError, match="not an InputProvider"):
            reg.register("bad", "not a class")  # type: ignore[arg-type]

    def test_register_non_provider_class(self) -> None:
        reg = InputProviderRegistry()
        with pytest.raises(TypeError, match="not an InputProvider"):
            reg.register("bad", object)  # type: ignore[arg-type]


class TestUnregister:
    def test_unregister_removes(self) -> None:
        reg = InputProviderRegistry()
        reg.register("x", _MinimalProvider)
        reg.unregister("x")
        assert reg.is_registered("x") is False

    def test_unregister_unknown_raises(self) -> None:
        reg = InputProviderRegistry()
        with pytest.raises(KeyError):
            reg.unregister("nonexistent")


class TestListProviders:
    def test_empty(self) -> None:
        reg = InputProviderRegistry()
        assert reg.list_providers() == []

    def test_sorted(self) -> None:
        reg = InputProviderRegistry()
        reg.register("z", _MinimalProvider)
        reg.register("a", _MinimalProvider)
        reg.register("m", _MinimalProvider)
        assert reg.list_providers() == ["a", "m", "z"]

    def test_after_unregister(self) -> None:
        reg = InputProviderRegistry()
        reg.register("keep", _MinimalProvider)
        reg.register("remove", _MinimalProvider)
        reg.unregister("remove")
        assert reg.list_providers() == ["keep"]


# ---------------------------------------------------------------------------
# Tests: factory creation
# ---------------------------------------------------------------------------


class TestCreate:
    def test_create_known(self) -> None:
        reg = InputProviderRegistry()
        reg.register("p", _MinimalProvider)
        instance = reg.create("p")
        assert isinstance(instance, _MinimalProvider)

    def test_create_unknown_raises(self) -> None:
        reg = InputProviderRegistry()
        with pytest.raises(KeyError):
            reg.create("nonexistent")

    def test_create_with_config(self) -> None:
        reg = InputProviderRegistry()
        reg.register("p", _MinimalProvider)
        instance = reg.create("p", {"key": "val"})
        assert isinstance(instance, _MinimalProvider)

    def test_create_propagates_constructor_args(self) -> None:
        registry_captures: list[dict | None] = []

        class _CapturingProvider(InputProvider):
            def __init__(self, config: dict | None = None) -> None:
                registry_captures.append(config)

            def connect(self) -> None: ...
            def disconnect(self) -> None: ...
            def is_connected(self) -> bool:
                return False

            @property
            def screen_size(self) -> tuple[int, int]:
                return (0, 0)

            def click(self, x, y, button="left"): ...
            def double_click(self, x, y): ...
            def right_click(self, x, y): ...
            def move_mouse(self, x, y, duration=0.0): ...
            def drag(self, x1, y1, x2, y2, duration=0.0): ...
            def scroll(self, clicks, x=None, y=None): ...
            def key_down(self, key): ...
            def key_up(self, key): ...
            def press_key(self, key): ...
            def type_text(self, text): ...
            def hotkey(self, *keys): ...
            def wait(self, seconds): ...
            def take_screenshot(self, path=None):
                return None

        reg = InputProviderRegistry()
        reg.register("capture", _CapturingProvider)
        reg.create("capture", {"executable": "adb"})
        assert registry_captures == [{"executable": "adb"}]

    def test_create_without_config(self) -> None:
        reg = InputProviderRegistry()
        reg.register("p", _MinimalProvider)
        instance = reg.create("p")
        assert isinstance(instance, _MinimalProvider)

    def test_create_many_instances(self) -> None:
        reg = InputProviderRegistry()
        reg.register("p", _MinimalProvider)
        instances = [reg.create("p") for _ in range(5)]
        assert len(set(id(i) for i in instances)) == 5


# ---------------------------------------------------------------------------
# Tests: thread safety
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_concurrent_register(self) -> None:
        reg = InputProviderRegistry()
        errors: list[Exception] = []
        lock = threading.Lock()

        def _register(name: str) -> None:
            try:
                reg.register(name, _MinimalProvider)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [
            threading.Thread(target=_register, args=("a",)),
            threading.Thread(target=_register, args=("b",)),
            threading.Thread(target=_register, args=("c",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert reg.list_providers() == ["a", "b", "c"]

    def test_concurrent_create(self) -> None:
        reg = InputProviderRegistry()
        reg.register("p", _MinimalProvider)
        results: list[bool] = []
        lock = threading.Lock()

        def _create() -> None:
            p = reg.create("p")
            with lock:
                results.append(isinstance(p, _MinimalProvider))

        threads = [threading.Thread(target=_create) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert all(results)
        assert len(results) == 20

    def test_concurrent_list_while_registering(self) -> None:
        reg = InputProviderRegistry()
        reg.register("existing", _MinimalProvider)
        errors: list[Exception] = []
        lock = threading.Lock()

        def _register_worker() -> None:
            for i in range(10):
                try:
                    reg.register(f"w{i}", _MinimalProvider)
                except ValueError:
                    pass
                except Exception as exc:
                    with lock:
                        errors.append(exc)

        def _list_worker() -> None:
            for _ in range(50):
                try:
                    _ = reg.list_providers()
                except Exception as exc:
                    with lock:
                        errors.append(exc)

        threads = [threading.Thread(target=_register_worker) for _ in range(3)]
        threads += [threading.Thread(target=_list_worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
