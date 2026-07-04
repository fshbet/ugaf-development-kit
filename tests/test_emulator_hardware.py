"""Tests for ugaf.emulator.hardware.HardwareDetector."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ugaf.emulator.hardware import HardwareDetector, HardwareInfo


def _mock_result(stdout: str = "", stderr: str = "", returncode: int = 0) -> MagicMock:
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


def test_detect_without_emulator_path_reports_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.cpu_count", lambda: 8)
    detector = HardwareDetector()
    monkeypatch.setattr(detector, "_detect_total_ram_mb", lambda: 16384)
    info = detector.detect(emulator_path=None)
    assert info.cpu_count == 8
    assert info.total_ram_mb == 16384
    assert info.accel_available is False
    assert info.accel_backend is None


def test_detect_parses_whpx_acceleration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_emulator = tmp_path / "emulator.exe"
    fake_emulator.write_text("fake")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        return _mock_result(stdout="accel:\n0\nWHPX(10.0.26200) is installed and usable.\naccel")

    monkeypatch.setattr(subprocess, "run", fake_run)
    detector = HardwareDetector()
    monkeypatch.setattr(detector, "_detect_total_ram_mb", lambda: 32768)
    monkeypatch.setattr("os.cpu_count", lambda: 16)

    info = detector.detect(emulator_path=fake_emulator)
    assert info.accel_available is True
    assel = info.accel_backend
    assert assel == "WHPX"


def test_detect_acceleration_not_usable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_emulator = tmp_path / "emulator.exe"
    fake_emulator.write_text("fake")

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        return _mock_result(stdout="accel:\n1\nHAXM is not installed.\naccel", returncode=1)

    monkeypatch.setattr(subprocess, "run", fake_run)
    detector = HardwareDetector()
    info = detector._detect_acceleration(fake_emulator)
    assert info[0] is False
    assert info[1] is None


@pytest.mark.parametrize(
    ("cpu", "ram_mb", "expected"),
    [
        (16, 32768, "gaming"),
        (12, 16384, "flagship"),
        (8, 8192, "mid_range"),
        (2, 2048, "low_end"),
    ],
)
def test_recommend_performance_profile(cpu: int, ram_mb: int, expected: str) -> None:
    detector = HardwareDetector()
    info = HardwareInfo(
        cpu_count=cpu,
        total_ram_mb=ram_mb,
        accel_available=True,
        accel_backend="WHPX",
        accel_message="",
    )
    assert detector.recommend_performance_profile(info) == expected


def test_ram_detection_failure_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_error(*args: object, **kwargs: object) -> None:
        raise OSError("boom")

    monkeypatch.setattr(subprocess, "run", raise_error)
    detector = HardwareDetector()
    assert detector._detect_total_ram_mb() == 0
