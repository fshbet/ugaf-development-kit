"""Tests for ugaf.apps.manager.ApplicationManager.

Uses a fake shell-capable DeviceProvider (real DeviceManager on top)
rather than mocking subprocess/adb directly — ApplicationManager's own
contract is "talks only to DeviceManager.execute_shell", so exercising
it against a fake transport is the right boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ugaf.apps.manager import ApplicationManager
from ugaf.apps.types import AppDefinition
from ugaf.device.exceptions import DeviceCommandError
from ugaf.device.manager import DeviceManager
from ugaf.platform.device import DeviceInfo, DeviceProvider, DeviceStatus

_DEVICE_ID = "d1"


class _ScriptedProvider(DeviceProvider):
    """Shell-capable fake transport whose responses are scripted per call."""

    def __init__(self, handler: Callable[[tuple[str, ...]], str]) -> None:
        self._handler = handler
        self.calls: list[tuple[str, ...]] = []
        self.devices = [
            DeviceInfo(
                id=_DEVICE_ID, name="Fake", status=DeviceStatus.ONLINE, platform="android",
                transport="fake",
            )
        ]

    def list_devices(self) -> list[DeviceInfo]:
        return list(self.devices)

    def get_device(self, device_id: str) -> DeviceInfo | None:
        return self.devices[0] if device_id == _DEVICE_ID else None

    def shell(self, device_id: str, *args: str) -> str:
        self.calls.append(args)
        return self._handler(args)


def _manager(
    handler: Callable[[tuple[str, ...]], str],
) -> tuple[ApplicationManager, _ScriptedProvider]:
    dm = DeviceManager()
    provider = _ScriptedProvider(handler)
    dm.register_provider("fake", provider)
    dm.discover()
    return ApplicationManager(dm), provider


def _app(**overrides: object) -> AppDefinition:
    base = {
        "name": "Test App",
        "package": "com.example.app",
        "launch_timeout": 0.2,
        "launch_retries": 0,
    }
    base.update(overrides)
    return AppDefinition(**base)  # type: ignore[arg-type]


class TestListAndInstalled:
    async def test_list_packages_parses_package_lines(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "package:com.a\npackage:com.b\n"

        manager, _ = _manager(handler)
        packages = await manager.list_packages(_DEVICE_ID)
        assert packages == ["com.a", "com.b"]

    async def test_list_packages_third_party_only_passes_dash3(self) -> None:
        seen = []

        def handler(args: tuple[str, ...]) -> str:
            seen.append(args)
            return ""

        manager, _ = _manager(handler)
        await manager.list_packages(_DEVICE_ID, third_party_only=True)
        assert "-3" in seen[0]
        seen.clear()
        await manager.list_packages(_DEVICE_ID, third_party_only=False)
        assert "-3" not in seen[0]

    async def test_is_installed_true(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "package:com.example.app\n"

        manager, _ = _manager(handler)
        assert await manager.is_installed(_DEVICE_ID, "com.example.app") is True

    async def test_is_installed_false_on_empty_output(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return ""

        manager, _ = _manager(handler)
        assert await manager.is_installed(_DEVICE_ID, "com.example.app") is False

    async def test_is_installed_false_on_substring_false_positive(self) -> None:
        # A device with "com.example.app.beta" installed should not match
        # a query for "com.example.app" via naive substring matching.
        def handler(args: tuple[str, ...]) -> str:
            return "package:com.example.app.beta\n"

        manager, _ = _manager(handler)
        assert await manager.is_installed(_DEVICE_ID, "com.example.app") is False

    async def test_get_version_parses_version_name(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "  versionName=1.2.3\n  other=stuff\n"

        manager, _ = _manager(handler)
        assert await manager.get_version(_DEVICE_ID, "com.example.app") == "1.2.3"

    async def test_get_version_none_when_missing(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "nothing useful here"

        manager, _ = _manager(handler)
        assert await manager.get_version(_DEVICE_ID, "com.example.app") is None


class TestForegroundPackage:
    async def test_parses_current_focus(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "mCurrentFocus=Window{abc u0 com.example.app/com.example.app.MainActivity}"

        manager, _ = _manager(handler)
        assert await manager.foreground_package(_DEVICE_ID) == "com.example.app"

    async def test_falls_back_to_resumed_activity(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            if args[:2] == ("dumpsys", "window"):
                return "no useful line here"
            return "  mResumedActivity: ActivityRecord{x u0 com.example.app/.MainActivity t1}"

        manager, _ = _manager(handler)
        assert await manager.foreground_package(_DEVICE_ID) == "com.example.app"

    async def test_returns_none_when_undetectable(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return "nothing recognizable"

        manager, _ = _manager(handler)
        assert await manager.foreground_package(_DEVICE_ID) is None


class TestLaunch:
    async def test_launch_uses_am_start_when_activity_given(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return ""

        manager, provider = _manager(handler)
        app = _app(launch_activity="com.example.app.Main")
        await manager.launch(_DEVICE_ID, app)
        assert provider.calls[-1] == ("am", "start", "-n", "com.example.app/com.example.app.Main")

    async def test_launch_uses_monkey_when_no_activity(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return ""

        manager, provider = _manager(handler)
        app = _app(launch_activity=None)
        await manager.launch(_DEVICE_ID, app)
        assert provider.calls[-1][:2] == ("monkey", "-p")


class TestLaunchAndWait:
    async def test_fails_fast_when_not_installed(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return ""  # pm list packages -> nothing -> not installed

        manager, provider = _manager(handler)
        result = await manager.launch_and_wait(_DEVICE_ID, _app())
        assert result.success is False
        assert "not installed" in (result.error or "")
        assert result.attempts == 0
        # Never attempted an actual launch.
        assert not any(c[0] == "am" or c[0] == "monkey" for c in provider.calls)

    async def test_succeeds_on_first_attempt(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            if args[:2] == ("pm", "list"):
                return "package:com.example.app\n"
            if args[:2] == ("dumpsys", "window"):
                return "mCurrentFocus=Window{a u0 com.example.app/.Main}"
            return ""

        manager, _ = _manager(handler)
        result = await manager.launch_and_wait(_DEVICE_ID, _app())
        assert result.success is True
        assert result.attempts == 1
        assert result.foreground_package == "com.example.app"

    async def test_retries_then_succeeds(self) -> None:
        state = {"launch_count": 0}

        def handler(args: tuple[str, ...]) -> str:
            if args[:2] == ("pm", "list"):
                return "package:com.example.app\n"
            if args[0] == "monkey":
                state["launch_count"] += 1
                return ""
            if args[:2] == ("dumpsys", "window"):
                # Only report foreground after the second launch attempt.
                if state["launch_count"] >= 2:
                    return "mCurrentFocus=Window{a u0 com.example.app/.Main}"
                return "mCurrentFocus=Window{a u0 com.other.app/.Main}"
            return ""

        manager, _ = _manager(handler)
        app = _app(launch_retries=2, launch_timeout=0.05)
        result = await manager.launch_and_wait(_DEVICE_ID, app)
        assert result.success is True
        assert result.attempts == 2

    async def test_exhausts_retries_and_reports_error(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            if args[:2] == ("pm", "list"):
                return "package:com.example.app\n"
            if args[:2] == ("dumpsys", "window"):
                return "mCurrentFocus=Window{a u0 com.other.app/.Main}"
            return ""

        manager, _ = _manager(handler)
        app = _app(launch_retries=1, launch_timeout=0.05)
        result = await manager.launch_and_wait(_DEVICE_ID, app)
        assert result.success is False
        assert result.attempts == 2
        assert "did not reach the foreground" in (result.error or "")
        assert result.foreground_package == "com.other.app"


class TestStop:
    async def test_stop_calls_force_stop(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            return ""

        manager, provider = _manager(handler)
        await manager.stop(_DEVICE_ID, "com.example.app")
        assert provider.calls[-1] == ("am", "force-stop", "com.example.app")


class TestApplicationManagerRecoversFromTransientShellFailure:
    async def test_foreground_package_returns_none_on_shell_error(self) -> None:
        def handler(args: tuple[str, ...]) -> str:
            raise DeviceCommandError("boom")

        manager, _ = _manager(handler)
        assert await manager.foreground_package(_DEVICE_ID) is None


def test_shadow_fight_3_app_definition_loads_from_real_file() -> None:
    app = AppDefinition.load(Path("games/shadow_fight_3/app.yaml"))
    assert app.name == "Shadow Fight 3"
    assert app.package == "com.nekki.shadowfight3"
    assert app.shutdown_behavior == "leave_running"
