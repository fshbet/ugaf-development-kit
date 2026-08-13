"""Tests for the one-click Create Virtual Device workflow (ADR-022).

Combines the two existing mocking patterns from this test suite:
``ugaf.webapp.session.EmulatorManager``/``EnvironmentChecker`` (from
``test_webapp_emulator_routes.py``) for the AVD create/start/boot-wait
steps, and a mocked ``adb`` subprocess (from ``test_webapp_server.py``)
so the subsequent device-connect pipeline (ADR-020) sees a real,
ADB-reachable, fully-booted device with the exact serial the mocked
``start()`` call reports -- end to end, one route call.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ugaf.emulator.dependencies import DependencyReport, DependencyStatus
from ugaf.emulator.types import AvdInfo, EmulatorInstanceHandle
from ugaf.webapp.server import create_app


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def _png_bytes() -> bytes:
    """A minimal valid 1x1 PNG, for the screenshot decode path."""
    import numpy

    from ugaf.imaging.opencv_backend import OpenCVBackend

    backend = OpenCVBackend()
    data = numpy.zeros((1, 1, 3), dtype=numpy.uint8)
    return backend.encode(data, fmt="png")


def _adb_side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
    if "devices" in cmd:
        return _mock_result("List of devices attached\nemulator-5554\tdevice\n")
    if "size" in cmd:
        return _mock_result("Physical size: 1080x1920\n")
    if any("boot_completed" in part for part in cmd):
        return _mock_result("1\n")
    if any("dev.bootcomplete" in part for part in cmd):
        return _mock_result("1\n")
    if any("bootanim" in part for part in cmd):
        return _mock_result("stopped\n")
    if "dumpsys" in cmd:
        return _mock_result("mCurrentFocus=Window{... com.android.launcher3/.Launcher}\n")
    if "screencap" in cmd:
        return _mock_result(stdout=_png_bytes() if not kwargs.get("text") else "")
    return _mock_result()


def _ok(name: str) -> DependencyStatus:
    return DependencyStatus(name, True, f"/fake/{name}", "")


def _ready_report() -> DependencyReport:
    return DependencyReport(
        android_studio=DependencyStatus("Android Studio", False, None, ""),
        sdk=_ok("sdk"),
        platform_tools=_ok("platform_tools"),
        emulator=_ok("emulator"),
        sdkmanager=_ok("sdkmanager"),
        avdmanager=_ok("avdmanager"),
        cmdline_tools_consistency=_ok("cmdline_tools"),
        hypervisor=_ok("hypervisor"),
    )


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
    manager.create.return_value = AvdInfo(
        name="MyAvd", device="pixel_9", target=None, abi="x86_64", path="p", valid=True
    )
    manager.start.return_value = EmulatorInstanceHandle(
        name="MyAvd",
        adb_serial="emulator-5554",
        console_port=5554,
        adb_port=5555,
        pid=1234,
        log_path="log",
        working_directory="wd",
    )
    manager.wait_until_booted.return_value = True
    manager.boot_timeout = 30.0
    manager.is_running.return_value = True
    return manager


@pytest.fixture
def client(app, emulator_manager: MagicMock):
    with (
        patch("ugaf.webapp.session.EmulatorManager", return_value=emulator_manager),
        patch("ugaf.webapp.session.EnvironmentChecker") as checker_cls,
        patch("ugaf.device.adb_provider.subprocess.run", side_effect=_adb_side_effect),
        TestClient(app) as test_client,
    ):
        checker_cls.return_value.check.return_value = _ready_report()
        yield test_client


def test_one_click_create_reaches_ready(client: TestClient, emulator_manager: MagicMock) -> None:
    res = client.post(
        "/api/emulator/avds/one-click",
        json={
            "name": "MyAvd",
            "manufacturer": "Google",
            "device_name": "pixel_9",
            "performance_profile": "mid_range",
            "capture_provider": "adb",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["device_id"] == "emulator-5554"
    assert body["avd_name"] == "MyAvd"
    assert body["state"] == "ready"
    emulator_manager.create.assert_called_once_with("MyAvd", "Google", "pixel_9", "mid_range")
    emulator_manager.start.assert_called_once_with("MyAvd")
    # BootMonitor (ADR-023) replaced the bare wait_until_booted() boolean call --
    # it uses is_running() plus real ADB/property probes instead.
    emulator_manager.is_running.assert_called_with("MyAvd")

    # The device is now genuinely connected -- not a separate manual step.
    devices = client.get("/api/devices").json()
    assert devices[0]["id"] == "emulator-5554"
    assert devices[0]["connected"] is True
    assert devices[0]["state"] == "ready"


def test_one_click_reports_invalid_avd_creation(
    client: TestClient, emulator_manager: MagicMock
) -> None:
    emulator_manager.create.return_value = AvdInfo(
        name="MyAvd",
        device=None,
        target=None,
        abi=None,
        path="p",
        valid=False,
        error="system image not available",
    )
    res = client.post(
        "/api/emulator/avds/one-click",
        json={"name": "MyAvd", "manufacturer": "Google", "device_name": "pixel_9"},
    )
    assert res.status_code == 400
    assert "system image not available" in res.json()["detail"]
    emulator_manager.start.assert_not_called()


def test_one_click_reports_exact_failed_stage_on_boot_failure(
    client: TestClient, emulator_manager: MagicMock
) -> None:
    """ADR-023: a crashed process is reported as a specific stage, not a generic timeout."""
    emulator_manager.is_running.return_value = False
    res = client.post(
        "/api/emulator/avds/one-click",
        json={"name": "MyAvd", "manufacturer": "Google", "device_name": "pixel_9"},
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "emulator_process" in detail
    assert "did not finish booting" in detail


def test_one_click_refuses_when_dependency_missing(app, emulator_manager: MagicMock) -> None:
    missing_report = DependencyReport(
        android_studio=DependencyStatus("Android Studio", False, None, ""),
        sdk=_ok("sdk"),
        platform_tools=_ok("platform_tools"),
        emulator=_ok("emulator"),
        sdkmanager=_ok("sdkmanager"),
        avdmanager=DependencyStatus("avdmanager", False, None, "avdmanager not found."),
        cmdline_tools_consistency=_ok("cmdline_tools"),
        hypervisor=_ok("hypervisor"),
    )
    with (
        patch("ugaf.webapp.session.EmulatorManager", return_value=emulator_manager),
        patch("ugaf.webapp.session.EnvironmentChecker") as checker_cls,
        TestClient(app) as client,
    ):
        checker_cls.return_value.check.return_value = missing_report
        res = client.post(
            "/api/emulator/avds/one-click",
            json={"name": "MyAvd", "manufacturer": "Google", "device_name": "pixel_9"},
        )
    assert res.status_code == 400
    assert "avdmanager" in res.json()["detail"]
    emulator_manager.start.assert_not_called()
