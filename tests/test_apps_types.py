"""Tests for ugaf.apps.types: AppDefinition/LaunchResult."""

from __future__ import annotations

from pathlib import Path

from ugaf.apps.types import AppDefinition, LaunchResult


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


def test_required_fields_and_defaults(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "app.yaml",
        """
name: My App
package: com.example.app
""",
    )
    app = AppDefinition.load(path)
    assert app.name == "My App"
    assert app.package == "com.example.app"
    assert app.launch_activity is None
    assert app.orientation is None
    assert app.launch_timeout == 15.0
    assert app.launch_retries == 2
    assert app.expected_startup_templates == ()
    assert app.expected_resolution is None
    assert app.shutdown_behavior == "leave_running"


def test_full_fields_parsed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "app.yaml",
        """
name: My App
package: com.example.app
launch_activity: com.example.app.MainActivity
orientation: landscape
launch_timeout: 30
launch_retries: 5
expected_startup_templates: [fight_button, menu]
expected_resolution: [1080, 2400]
shutdown_behavior: force_stop
""",
    )
    app = AppDefinition.load(path)
    assert app.launch_activity == "com.example.app.MainActivity"
    assert app.orientation == "landscape"
    assert app.launch_timeout == 30.0
    assert app.launch_retries == 5
    assert app.expected_startup_templates == ("fight_button", "menu")
    assert app.expected_resolution == (1080, 2400)
    assert app.shutdown_behavior == "force_stop"


def test_launch_result_is_a_plain_frozen_dataclass() -> None:
    result = LaunchResult(
        success=True, package="com.example.app", foreground_package="com.example.app",
        attempts=1, elapsed=0.5,
    )
    assert result.error is None
    assert result.success is True
