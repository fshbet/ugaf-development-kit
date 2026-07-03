"""Tests for the UGAF web control panel's FastAPI backend.

All ADB subprocess calls are mocked at the single real ``subprocess.run``
target — ``ugaf.device.adb_provider`` and ``ugaf.vision.adb_screenshot``
both do a plain ``import subprocess``, so they share the exact same
module object; patching ``run`` via either import path patches the
same global attribute, and a second unconfigured patch on the "other"
path would silently clobber the first. One patch, with a side effect
that inspects the command, covers every ADB-backed provider — no real
``adb`` binary or connected device required, CI-safe on any runner.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ugaf.webapp.server import create_app


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


_DEVICES_OUTPUT = "List of devices attached\nfake-serial-1\tdevice product:x model:TestPhone\n"


@pytest.fixture
def app(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("logging:\n  level: INFO\n")
    games_dir = tmp_path / "games"
    games_dir.mkdir()
    return create_app(config_path=config_path, games_dir=games_dir)


def _adb_side_effect(cmd: list[str], **kwargs: object) -> MagicMock:
    """Return a canned response appropriate to the ADB subcommand being run."""
    if "devices" in cmd:
        return _mock_result(_DEVICES_OUTPUT)
    if "size" in cmd:
        return _mock_result("Physical size: 1080x1920\n")
    if "screencap" in cmd:
        # exec-out uses capture_output=True without text=True, so stdout is bytes.
        return _mock_result(stdout=_png_bytes() if not kwargs.get("text") else "")
    return _mock_result()


@pytest.fixture
def adb_mock():
    # Patching either import path patches the same shared `subprocess` module
    # object — see the module docstring.
    with patch("ugaf.device.adb_provider.subprocess.run", side_effect=_adb_side_effect) as mock_run:
        yield mock_run


class TestHealthAndBasics:
    def test_health(self, app) -> None:
        with TestClient(app) as client:
            res = client.get("/api/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}

    def test_index_serves_html(self, app) -> None:
        with TestClient(app) as client:
            res = client.get("/")
        assert res.status_code == 200
        assert "UGAF Control Panel" in res.text

    def test_static_files_served(self, app) -> None:
        with TestClient(app) as client:
            res = client.get("/static/app.js")
        assert res.status_code == 200


class TestDevices:
    def test_list_devices(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            res = client.get("/api/devices")
        assert res.status_code == 200
        devices = res.json()
        assert len(devices) == 1
        assert devices[0]["id"] == "fake-serial-1"
        assert devices[0]["status"] == "online"
        assert devices[0]["connected"] is False

    def test_connect_and_disconnect(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            res = client.post("/api/devices/fake-serial-1/connect")
            assert res.status_code == 200
            assert res.json()["connected"] is True

            devices = client.get("/api/devices").json()
            assert devices[0]["connected"] is True

            res = client.post("/api/devices/fake-serial-1/disconnect")
            assert res.status_code == 200
            assert res.json()["connected"] is False

    def test_screenshot_requires_connection(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            res = client.get("/api/devices/fake-serial-1/screenshot")
        assert res.status_code == 409

    def test_tap_requires_connection(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            res = client.post("/api/devices/fake-serial-1/tap", json={"x": 1, "y": 2})
        assert res.status_code == 409


class TestScreenshotAndActions:
    def test_screenshot_after_connect(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            client.post("/api/devices/fake-serial-1/connect")
            res = client.get("/api/devices/fake-serial-1/screenshot")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"

    def test_tap_after_connect(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            client.post("/api/devices/fake-serial-1/connect")
            res = client.post("/api/devices/fake-serial-1/tap", json={"x": 100, "y": 200})
        assert res.status_code == 200
        assert res.json()["tapped"] == [100, 200]

    def test_swipe_after_connect(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            client.post("/api/devices/fake-serial-1/connect")
            res = client.post(
                "/api/devices/fake-serial-1/swipe",
                json={"x1": 0, "y1": 0, "x2": 100, "y2": 100, "duration": 0.1},
            )
        assert res.status_code == 200
        assert res.json()["swiped"] is True

    def test_text_after_connect(self, app, adb_mock: MagicMock) -> None:
        with TestClient(app) as client:
            client.post("/api/devices/fake-serial-1/connect")
            res = client.post("/api/devices/fake-serial-1/text", json={"text": "hello"})
        assert res.status_code == 200
        assert res.json()["typed"] == "hello"


class TestPlugins:
    def test_list_plugins_empty_games_dir(self, app) -> None:
        with TestClient(app) as client:
            res = client.get("/api/plugins")
        assert res.status_code == 200
        assert res.json() == []

    def test_list_plugins_finds_real_demo_workflow(self) -> None:
        demo_app = create_app(games_dir=Path("games"))
        with TestClient(demo_app) as client:
            res = client.get("/api/plugins")
        ids = {p["id"] for p in res.json()}
        assert "demo_workflow" in ids
        assert "example_game" in ids

    def test_run_unknown_plugin_returns_400(self, app) -> None:
        with TestClient(app) as client:
            res = client.post("/api/plugins/nonexistent/run")
        assert res.status_code == 400

    def test_run_succeeds_after_a_prior_health_check(self) -> None:
        """Regression test: polling health before Run must not break Run.

        ``plugin_health()`` calls ``PluginManager.load()`` as a side
        effect (to build the lifecycle wrapper), which leaves the
        plugin in ``GameState.CREATED`` — the automation list's status
        polling does exactly this before a user ever clicks "Run". Run
        must still succeed from that state, not 400 with "Cannot
        transition from 'created' to 'running'".
        """
        demo_app = create_app(games_dir=Path("games"))
        with TestClient(demo_app) as client:
            health_res = client.get("/api/plugins/demo_workflow/health")
            assert health_res.status_code == 200
            assert health_res.json()["status"] == "created"

            run_res = client.post("/api/plugins/demo_workflow/run")
            assert run_res.status_code == 200


class TestLogs:
    def test_logs_returns_list(self, app) -> None:
        with TestClient(app) as client:
            res = client.get("/api/logs")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_logs_since_offset(self, app) -> None:
        with TestClient(app) as client:
            all_logs = client.get("/api/logs").json()
            partial = client.get(f"/api/logs?since={len(all_logs)}").json()
        assert partial == []


def _png_bytes() -> bytes:
    """A minimal valid 1x1 PNG, for the screenshot decode path."""
    import numpy

    from ugaf.imaging.opencv_backend import OpenCVBackend

    backend = OpenCVBackend()
    data = numpy.zeros((1, 1, 3), dtype=numpy.uint8)
    return backend.encode(data, fmt="png")
