"""Tests for the Emulator Manager routes in ugaf.webapp.server.

Mocks at ``ugaf.webapp.session.EmulatorManager`` (the name imported
into the session module) so these routes are exercised without a real
Android SDK -- ``ugaf.emulator``'s own test suite already covers the
real SDK-invocation logic these routes delegate to.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle
from ugaf.webapp.server import create_app


@pytest.fixture
def app(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("logging:\n  level: INFO\n")
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    return create_app(config_path=config_path, games_dir=games_dir)


@pytest.fixture
def emulator_manager() -> MagicMock:
    manager = MagicMock()
    manager.sdk_paths.sdk_root = Path("/fake/sdk")
    return manager


@pytest.fixture
def client(app, emulator_manager: MagicMock):
    with (
        patch("ugaf.webapp.session.EmulatorManager", return_value=emulator_manager),
        TestClient(app) as test_client,
    ):
        yield test_client


def test_emulator_status_reports_full_dependency_list(app) -> None:
    from ugaf.emulator.dependencies import DependencyReport, DependencyStatus

    def ok(name: str, path: str) -> DependencyStatus:
        return DependencyStatus(name, True, path, "")

    report = DependencyReport(
        android_studio=DependencyStatus("Android Studio", False, None, "not found anywhere"),
        sdk=ok("Android SDK", "/fake/sdk"),
        platform_tools=ok("Platform Tools (adb)", "/fake/sdk/adb"),
        emulator=ok("Android Emulator (emulator.exe)", "/fake/sdk/emulator"),
        sdkmanager=ok("sdkmanager", "/fake/sdk/sdkmanager"),
        avdmanager=ok("avdmanager", "/fake/sdk/avdmanager"),
    )
    with (
        patch("ugaf.webapp.session.EnvironmentChecker") as checker_cls,
        TestClient(app) as client,
    ):
        checker_cls.return_value.check.return_value = report
        res = client.get("/api/emulator/status")

    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True  # Android Studio absence never blocks.
    assert body["error"] is None
    names = [d["name"] for d in body["dependencies"]]
    assert names == [
        "Android Studio",
        "Android SDK",
        "Platform Tools (adb)",
        "Android Emulator (emulator.exe)",
        "sdkmanager",
        "avdmanager",
    ]
    assert body["dependencies"][0]["found"] is False


def test_emulator_status_reports_blocking_error_when_sdk_missing(app) -> None:
    from ugaf.emulator.dependencies import DependencyReport, DependencyStatus

    def missing(name: str) -> DependencyStatus:
        return DependencyStatus(name, False, None, f"{name} not found. Fix: install it.")

    report = DependencyReport(
        android_studio=DependencyStatus("Android Studio", False, None, ""),
        sdk=missing("Android SDK"),
        platform_tools=missing("Platform Tools (adb)"),
        emulator=missing("Android Emulator (emulator.exe)"),
        sdkmanager=missing("sdkmanager"),
        avdmanager=missing("avdmanager"),
    )
    with (
        patch("ugaf.webapp.session.EnvironmentChecker") as checker_cls,
        TestClient(app) as client,
    ):
        checker_cls.return_value.check.return_value = report
        res = client.get("/api/emulator/status")

    body = res.json()
    assert body["available"] is False
    assert "Android SDK" in body["error"]
    assert "Fix: install it" in body["error"]


def test_list_manufacturers_delegates_to_emulator_manager(
    client: TestClient, emulator_manager: MagicMock
) -> None:
    emulator_manager.list_manufacturers.return_value = ["Google", "Samsung"]
    res = client.get("/api/emulator/manufacturers")
    assert res.status_code == 200
    assert res.json() == ["Google", "Samsung"]


def test_list_manufacturers_returns_503_when_sdk_unavailable(app) -> None:
    with (
        patch("ugaf.webapp.session.EmulatorManager", side_effect=Exception("SDK not found")),
        TestClient(app) as client,
    ):
        res = client.get("/api/emulator/manufacturers")
    assert res.status_code == 503


def test_check_system_image_route(client: TestClient, emulator_manager: MagicMock) -> None:
    emulator_manager.check_system_image.return_value = True
    res = client.get("/api/emulator/manufacturers/Google/devices/pixel_9/system-image")
    assert res.status_code == 200
    assert res.json() == {"installed": True}
    emulator_manager.check_system_image.assert_called_once_with("Google", "pixel_9")


def test_create_avd_route(client: TestClient, emulator_manager: MagicMock) -> None:
    emulator_manager.create.return_value = AvdInfo(
        name="MyAvd", device="pixel_9", target=None, abi="x86_64", path="x", valid=True
    )
    res = client.post(
        "/api/emulator/avds",
        json={
            "name": "MyAvd",
            "manufacturer": "Google",
            "device_name": "pixel_9",
            "performance_profile": "mid_range",
        },
    )
    assert res.status_code == 200
    assert res.json() == {"name": "MyAvd", "valid": True, "error": None}
    emulator_manager.create.assert_called_once_with("MyAvd", "Google", "pixel_9", "mid_range")


def test_create_avd_route_reports_error_on_failure(
    client: TestClient, emulator_manager: MagicMock
) -> None:
    emulator_manager.create.side_effect = Exception("system image not available")
    res = client.post(
        "/api/emulator/avds",
        json={
            "name": "MyAvd",
            "manufacturer": "Google",
            "device_name": "pixel_9",
            "performance_profile": "mid_range",
        },
    )
    assert res.status_code == 400
    assert "system image not available" in res.json()["detail"]


def test_start_avd_route(client: TestClient, emulator_manager: MagicMock) -> None:
    emulator_manager.start.return_value = EmulatorInstanceHandle(
        name="MyAvd",
        adb_serial="emulator-5554",
        console_port=5554,
        adb_port=5555,
        pid=1234,
        log_path="log",
        working_directory="wd",
    )
    res = client.post("/api/emulator/avds/MyAvd/start")
    assert res.status_code == 200
    assert res.json()["adb_serial"] == "emulator-5554"


def test_stop_avd_route(client: TestClient, emulator_manager: MagicMock) -> None:
    res = client.post("/api/emulator/avds/MyAvd/stop")
    assert res.status_code == 200
    assert res.json() == {"stopped": "MyAvd"}
    emulator_manager.stop.assert_called_once_with("MyAvd")


def test_delete_avd_route(client: TestClient, emulator_manager: MagicMock) -> None:
    res = client.delete("/api/emulator/avds/MyAvd")
    assert res.status_code == 200
    assert res.json() == {"deleted": "MyAvd"}
    emulator_manager.delete.assert_called_once_with("MyAvd")


def test_rename_avd_route(client: TestClient, emulator_manager: MagicMock) -> None:
    res = client.post("/api/emulator/avds/OldName/rename", json={"new_name": "NewName"})
    assert res.status_code == 200
    assert res.json() == {"renamed": "OldName", "new_name": "NewName"}
    emulator_manager.rename.assert_called_once_with("OldName", "NewName")


def test_rename_avd_route_reports_error(client: TestClient, emulator_manager: MagicMock) -> None:
    emulator_manager.rename.side_effect = Exception("AVD 'OldName' already exists")
    res = client.post("/api/emulator/avds/OldName/rename", json={"new_name": "NewName"})
    assert res.status_code == 400
