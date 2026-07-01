"""Tests for the InputManager."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import yaml

from ugaf.core.config import Config
from ugaf.input.exceptions import (
    ConnectionFailedError,
    CoordinateOutOfBoundsError,
    DeviceNotFoundError,
    ProviderNotAvailableError,
)
from ugaf.input.manager import InputManager, _validate_coordinates
from ugaf.input.provider import InputProvider
from ugaf.input.registry import InputProviderRegistry
from ugaf.input.types import Button, Key

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _make_provider_cls(**overrides: object) -> type[InputProvider]:
    """Dynamically create an InputProvider subclass with one-line stubs.

    Keyword arguments override default method stubs (e.g.
    ``connect=lambda s: raise_(ConnectionFailedError("fail"))``).
    """
    defaults = {
        name: lambda s, *a, **kw: None
        for name in (
            "connect",
            "disconnect",
            "click",
            "double_click",
            "right_click",
            "move_mouse",
            "drag",
            "scroll",
            "key_down",
            "key_up",
            "press_key",
            "type_text",
            "hotkey",
            "wait",
        )
    }
    defaults["is_connected"] = lambda s: True  # type: ignore[misc,assignment]
    defaults["take_screenshot"] = lambda s, path=None: None  # type: ignore[misc]
    defaults["screen_size"] = property(lambda s: (1920, 1080))  # type: ignore[assignment]
    defaults["__init__"] = lambda s, config=None: None  # type: ignore[misc]
    defaults.update(overrides)  # type: ignore[arg-type]
    return type("_DynamicInputProvider", (InputProvider,), defaults)


class _MockProvider(InputProvider):
    """InputProvider stub that delegates all methods to ``.mock``.

    Usage::

        reg.register("mock", _MockProvider)
        mgr = InputManager(cfg, registry=reg)
        mgr.connect()
        provider: _MockProvider = mgr._provider  # type: ignore[assignment]
        provider.mock.connect.assert_called_once()
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self.mock = MagicMock(spec=InputProvider)

    @property
    def screen_size(self) -> tuple[int, int]:
        return self.mock.screen_size  # type: ignore[no-any-return]

    def connect(self) -> None:
        self.mock.connect()

    def disconnect(self) -> None:
        self.mock.disconnect()

    def is_connected(self) -> bool:
        return self.mock.is_connected()  # type: ignore[no-any-return]

    def click(self, x: int, y: int, button: Button = "left") -> None:
        self.mock.click(x, y, button=button)

    def double_click(self, x: int, y: int) -> None:
        self.mock.double_click(x, y)

    def right_click(self, x: int, y: int) -> None:
        self.mock.right_click(x, y)

    def move_mouse(self, x: int, y: int, duration: float = 0.0) -> None:
        self.mock.move_mouse(x, y, duration=duration)

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.0,
    ) -> None:
        self.mock.drag(x1, y1, x2, y2, duration=duration)

    def scroll(
        self,
        clicks: int,
        x: int | None = None,
        y: int | None = None,
    ) -> None:
        self.mock.scroll(clicks, x=x, y=y)

    def key_down(self, key: Key) -> None:
        self.mock.key_down(key)

    def key_up(self, key: Key) -> None:
        self.mock.key_up(key)

    def press_key(self, key: Key) -> None:
        self.mock.press_key(key)

    def type_text(self, text: str) -> None:
        self.mock.type_text(text)

    def hotkey(self, *keys: Key) -> None:
        self.mock.hotkey(*keys)

    def wait(self, seconds: float) -> None:
        self.mock.wait(seconds)

    def take_screenshot(self, path: str | None = None) -> bytes | None:
        return self.mock.take_screenshot(path=path)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config(tmp_path: Path) -> Config:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "input": {
                    "provider": "test",
                    "dry_run": False,
                    "verbose": True,
                    "retry": {"count": 1, "delay": 0.01},
                    "delays": {"mouse": 0.0, "keyboard": 0.0},
                }
            }
        )
    )
    return Config(cfg_file)


# ---------------------------------------------------------------------------
# Tests: connect / lifecycle
# ---------------------------------------------------------------------------


class TestConnect:
    def test_known_provider(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "mock"}}))
        cfg = Config(cfg_file)
        reg = InputProviderRegistry()
        reg.register("mock", _MockProvider)
        mgr = InputManager(cfg, registry=reg)
        mgr.connect()
        assert isinstance(mgr._provider, _MockProvider)

    def test_unknown_provider(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "xyz"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg)
        with pytest.raises(ProviderNotAvailableError, match="xyz"):
            mgr.connect()

    def test_retry_logic(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump(
                {
                    "input": {
                        "provider": "retry_test",
                        "retry": {"count": 3, "delay": 0.01},
                    }
                }
            )
        )
        cfg = Config(cfg_file)

        call_count: int = 0

        def _connect_with_retries(self: object) -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionFailedError(f"fail{call_count}")

        cls = _make_provider_cls(connect=_connect_with_retries)
        reg = InputProviderRegistry()
        reg.register("retry_test", cls)
        mgr = InputManager(cfg, registry=reg)
        mgr.connect()
        assert call_count == 3

    def test_retry_exhausted(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump(
                {
                    "input": {
                        "provider": "fail_test",
                        "retry": {"count": 2, "delay": 0.01},
                    }
                }
            )
        )
        cfg = Config(cfg_file)

        def _always_fail(self: object) -> None:
            raise ConnectionFailedError("always fails")

        cls = _make_provider_cls(connect=_always_fail)
        reg = InputProviderRegistry()
        reg.register("fail_test", cls)
        mgr = InputManager(cfg, registry=reg)
        with pytest.raises(ConnectionFailedError, match="after 2 attempts"):
            mgr.connect()

    def test_default_provider_is_platform_aware(self, tmp_path: Path) -> None:
        """When ``input.provider`` is unset, the default is derived from detect_platform()."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({}))
        cfg = Config(cfg_file)
        windows_cls = _make_provider_cls()
        adb_cls = _make_provider_cls()
        reg = InputProviderRegistry()
        reg.register("windows", windows_cls)
        reg.register("adb", adb_cls)
        mgr = InputManager(cfg, registry=reg)

        from ugaf.core.platform import PlatformInfo

        with patch("ugaf.input.manager.detect_platform") as mock_detect:
            mock_detect.return_value = PlatformInfo(
                system="Linux",
                is_wsl=False,
                is_64bit=True,
                python_version="3.13.0",
                machine="x86_64",
                processor="",
                release="",
            )
            mgr.connect()
        assert isinstance(mgr._provider, adb_cls)

        mgr2 = InputManager(cfg, registry=reg)
        with patch("ugaf.input.manager.detect_platform") as mock_detect:
            mock_detect.return_value = PlatformInfo(
                system="Windows",
                is_wsl=False,
                is_64bit=True,
                python_version="3.13.0",
                machine="AMD64",
                processor="",
                release="",
            )
            mgr2.connect()
        assert isinstance(mgr2._provider, windows_cls)

    def test_context_manager(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "ctx_test"}}))
        cfg = Config(cfg_file)

        connect_mock = MagicMock()
        disconnect_mock = MagicMock()

        def _connect(self: object) -> None:
            connect_mock()

        def _disconnect(self: object) -> None:
            disconnect_mock()

        cls = _make_provider_cls(connect=_connect, disconnect=_disconnect)
        reg = InputProviderRegistry()
        reg.register("ctx_test", cls)
        mgr = InputManager(cfg, registry=reg)

        with mgr:
            assert mgr._provider is not None
            connect_mock.assert_called_once()
        disconnect_mock.assert_called_once()


class TestDisconnect:
    def test_disconnect_calls_provider(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock()
        mgr._provider = provider
        mgr.disconnect()
        provider.disconnect.assert_called_once()

    def test_disconnect_no_provider(self, config: Config) -> None:
        mgr = InputManager(config)
        mgr.disconnect()


# ---------------------------------------------------------------------------
# Tests: input operations
# ---------------------------------------------------------------------------


class TestInputOperations:
    def test_click(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr._screen_size = (1920, 1080)
        mgr.click(100, 200)
        provider.click.assert_called_once_with(100, 200, button="left")

    def test_click_out_of_bounds(self, config: Config) -> None:
        mgr = InputManager(config)
        mgr._provider = MagicMock(spec=InputProvider)
        mgr._screen_size = (100, 100)
        with pytest.raises(CoordinateOutOfBoundsError):
            mgr.click(200, 50)

    def test_double_click(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr._screen_size = (1920, 1080)
        mgr.double_click(50, 60)
        provider.double_click.assert_called_once_with(50, 60)

    def test_right_click(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr._screen_size = (1920, 1080)
        mgr.right_click(30, 40)
        provider.right_click.assert_called_once_with(30, 40)

    def test_move_mouse(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr._screen_size = (1920, 1080)
        mgr.move_mouse(500, 600, duration=0.2)
        provider.move_mouse.assert_called_once_with(500, 600, duration=0.2)

    def test_drag(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr._screen_size = (1920, 1080)
        mgr.drag(0, 0, 100, 200)
        provider.drag.assert_called_once_with(0, 0, 100, 200, duration=0.0)

    def test_scroll(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.scroll(-5)
        provider.scroll.assert_called_once_with(-5, x=None, y=None)

    def test_key_down(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.key_down("ctrl")
        provider.key_down.assert_called_once_with("ctrl")

    def test_key_up(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.key_up("shift")
        provider.key_up.assert_called_once_with("shift")

    def test_press_key(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.press_key("enter")
        provider.press_key.assert_called_once_with("enter")

    def test_type_text(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.type_text("hello")
        provider.type_text.assert_called_once_with("hello")

    def test_hotkey(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.hotkey("ctrl", "c")
        provider.hotkey.assert_called_once_with("ctrl", "c")

    def test_wait(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        with patch("ugaf.input.manager.time.sleep"):
            mgr.wait(1.0)
        provider.wait.assert_called_once_with(1.0)

    def test_screenshot(self, config: Config) -> None:
        mgr = InputManager(config)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        provider.take_screenshot.return_value = b"PNG..."
        result = mgr.take_screenshot()
        assert result == b"PNG..."
        provider.take_screenshot.assert_called_once_with(path=None)

    def test_operations_raise_when_disconnected(self, config: Config) -> None:
        mgr = InputManager(config)
        with pytest.raises(ConnectionFailedError, match="not connected"):
            mgr.click(0, 0)


# ---------------------------------------------------------------------------
# Tests: dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_skips_provider(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "windows", "dry_run": True}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg)
        provider = MagicMock(spec=InputProvider)
        mgr._provider = provider
        mgr.click(100, 200)
        provider.click.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: coordinate validation
# ---------------------------------------------------------------------------


class TestCoordinateValidation:
    def test_valid_coordinates(self) -> None:
        _validate_coordinates(100, 200, (1920, 1080))

    def test_out_of_bounds_x_negative(self) -> None:
        with pytest.raises(CoordinateOutOfBoundsError):
            _validate_coordinates(-1, 100, (1920, 1080))

    def test_out_of_bounds_x_too_large(self) -> None:
        with pytest.raises(CoordinateOutOfBoundsError):
            _validate_coordinates(1920, 100, (1920, 1080))

    def test_out_of_bounds_y_negative(self) -> None:
        with pytest.raises(CoordinateOutOfBoundsError):
            _validate_coordinates(100, -1, (1920, 1080))

    def test_out_of_bounds_y_too_large(self) -> None:
        with pytest.raises(CoordinateOutOfBoundsError):
            _validate_coordinates(100, 1080, (1920, 1080))

    def test_no_screen_size_skips_validation(self) -> None:
        _validate_coordinates(-1, -1, None)


# ---------------------------------------------------------------------------
# Tests: device-scoped targeting (Milestone 4)
# ---------------------------------------------------------------------------


class TestDeviceScopedTargeting:
    def test_device_id_overrides_config_default_device(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump({"input": {"provider": "adb", "adb": {"default_device": "from-config"}}})
        )
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_id="explicit-override")
        assert mgr._target_device_id() == "explicit-override"

    def test_falls_back_to_config_default_device(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            yaml.dump({"input": {"provider": "adb", "adb": {"default_device": "from-config"}}})
        )
        cfg = Config(cfg_file)
        mgr = InputManager(cfg)
        assert mgr._target_device_id() == "from-config"

    def test_two_managers_share_config_but_target_different_devices(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)

        mgr_a = InputManager(cfg, device_id="device-A")
        mgr_b = InputManager(cfg, device_id="device-B")

        assert mgr_a._target_device_id() == "device-A"
        assert mgr_b._target_device_id() == "device-B"

    def test_no_device_manager_skips_status_check(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_id="device-A")
        mgr._check_device_status_via_manager()  # should not raise (no device_manager)

    def test_online_device_passes_status_check(self, tmp_path: Path) -> None:
        from ugaf.device.manager import DeviceManager
        from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

        class _Provider(DeviceProvider):
            def list_devices(self) -> list[DeviceInfo]:
                return [
                    DeviceInfo(
                        id="device-A",
                        name="A",
                        status=DeviceStatus.ONLINE,
                        platform="android",
                        transport="fake",
                    )
                ]

            def get_device(self, device_id: str) -> DeviceInfo | None:
                return self.list_devices()[0] if device_id == "device-A" else None

        dm = DeviceManager()
        dm.register_provider("fake", _Provider())
        dm.discover()

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_id="device-A", device_manager=dm)
        mgr._check_device_status_via_manager()  # should not raise

    def test_unauthorized_device_raises_with_precise_status(self, tmp_path: Path) -> None:
        from ugaf.device.manager import DeviceManager
        from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

        class _Provider(DeviceProvider):
            def list_devices(self) -> list[DeviceInfo]:
                return [
                    DeviceInfo(
                        id="device-A",
                        name="A",
                        status=DeviceStatus.UNAUTHORIZED,
                        platform="android",
                        transport="fake",
                    )
                ]

            def get_device(self, device_id: str) -> DeviceInfo | None:
                return self.list_devices()[0] if device_id == "device-A" else None

        dm = DeviceManager()
        dm.register_provider("fake", _Provider())

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_id="device-A", device_manager=dm)

        with pytest.raises(DeviceNotFoundError, match="unauthorized"):
            mgr._check_device_status_via_manager()

    def test_unknown_device_id_is_not_flagged(self, tmp_path: Path) -> None:
        """No target device configured: the check is a no-op, not an error."""
        from ugaf.device.manager import DeviceManager

        dm = DeviceManager()
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_manager=dm)
        mgr._check_device_status_via_manager()  # no device_id at all -> no-op

    def test_connect_with_unauthorized_device_raises_before_provider_created(
        self, tmp_path: Path
    ) -> None:
        from ugaf.device.manager import DeviceManager
        from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

        class _Provider(DeviceProvider):
            def list_devices(self) -> list[DeviceInfo]:
                return [
                    DeviceInfo(
                        id="device-A",
                        name="A",
                        status=DeviceStatus.OFFLINE,
                        platform="android",
                        transport="fake",
                    )
                ]

            def get_device(self, device_id: str) -> DeviceInfo | None:
                return self.list_devices()[0] if device_id == "device-A" else None

        dm = DeviceManager()
        dm.register_provider("fake", _Provider())

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({"input": {"provider": "adb"}}))
        cfg = Config(cfg_file)
        mgr = InputManager(cfg, device_id="device-A", device_manager=dm)

        with pytest.raises(DeviceNotFoundError, match="offline"):
            mgr.connect()
        assert mgr._provider is None
