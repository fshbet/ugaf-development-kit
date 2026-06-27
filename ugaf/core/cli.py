"""Command-line interface for the UGAF framework."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

from ugaf.core.bootstrap import Application
from ugaf.core.health import HealthStatus

__all__ = [
    "CliConfig",
    "build_parser",
    "run_cli",
]

_UGAF_VERSION = "1.0.0a1"


@dataclass
class CliConfig:
    """Configuration parsed from CLI arguments.

    Attributes:
        command: The subcommand to execute.
        config_path: Path to the configuration file.
        games_dir: Path to the games plugin directory.
        verbose: Enable verbose output.

    """

    command: str
    config_path: Path
    games_dir: Path
    verbose: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the UGAF CLI.

    Returns:
        Configured ``ArgumentParser`` instance.

    """
    parser = argparse.ArgumentParser(
        prog="ugaf",
        description="Universal Game Automation Framework",
    )
    parser.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to configuration file (default: config/default.yaml)",
    )
    parser.add_argument(
        "--games-dir",
        default="games",
        help="Path to games plugin directory (default: games)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ugaf {_UGAF_VERSION}",
    )

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("start", help="Start the application")
    subparsers.add_parser("stop", help="Stop the application")
    subparsers.add_parser("health", help="Show health check status")
    subparsers.add_parser("plugins", help="List discovered plugins")
    subparsers.add_parser("version", help="Show version information")

    return parser


async def _cmd_start(config_path: Path, games_dir: Path) -> int:
    """Execute the ``start`` command.

    Initializes and starts the application, then waits for shutdown.

    """
    app = Application(config_path=config_path, games_dir=games_dir)
    await app.run_forever()
    return 0


async def _cmd_health(config_path: Path, games_dir: Path) -> int:
    """Execute the ``health`` command.

    Initializes the application and runs health checks.

    """
    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()
    results = await app.health()

    healthy = 0
    warnings = 0
    errors = 0

    for result in results:
        status_icon = {
            HealthStatus.HEALTHY: "[OK]",
            HealthStatus.WARNING: "[WARN]",
            HealthStatus.ERROR: "[ERR]",
        }
        icon = status_icon.get(result.status, "[?]")
        print(f"  {icon} {result.component}: {result.message}")
        if result.status is HealthStatus.HEALTHY:
            healthy += 1
        elif result.status is HealthStatus.WARNING:
            warnings += 1
        else:
            errors += 1

    print(f"\n{healthy} healthy, {warnings} warnings, {errors} errors")

    if errors > 0:
        return 1
    if warnings > 0:
        return 2
    return 0


async def _cmd_plugins(config_path: Path, games_dir: Path) -> int:
    """Execute the ``plugins`` command.

    Discovers and lists all plugins.

    """
    app = Application(config_path=config_path, games_dir=games_dir)
    await app.initialize()

    plugins = app.plugin_loader
    if plugins is None:
        print("Plugin loader not available")
        return 1

    discovered = plugins.discover()
    if not discovered:
        print("No plugins discovered")
        return 0

    print(f"Discovered {len(discovered)} plugin(s):\n")
    for plugin in discovered:
        print(f"  {plugin.manifest.name} v{plugin.manifest.version}")
        print(f"    Directory: {plugin.directory}")
        modules = []
        if plugin.bot_module:
            modules.append("bot")
        if plugin.vision_module:
            modules.append("vision")
        if plugin.strategy_module:
            modules.append("strategy")
        if modules:
            print(f"    Modules: {', '.join(modules)}")
        print()

    return 0


async def _cmd_version() -> int:
    """Execute the ``version`` command."""
    from ugaf.core.platform import detect_platform

    info = detect_platform()
    print(f"UGAF version: {_UGAF_VERSION}")
    print(f"Python:       {info.python_version}")
    print(f"Platform:     {info.system} {info.release} ({info.machine})")
    print(f"WSL:          {'Yes' if info.is_wsl else 'No'}")
    return 0


def run_cli(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and execute the requested command.

    Args:
        argv: Command-line arguments (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 for success, 1 for errors).

    """
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    games_dir = Path(args.games_dir)

    command = args.command
    if command is None:
        parser.print_help()
        return 1

    if command == "version":
        return asyncio.run(_cmd_version())

    if command == "start":
        return asyncio.run(_cmd_start(config_path, games_dir))
    if command == "health":
        return asyncio.run(_cmd_health(config_path, games_dir))
    if command == "plugins":
        return asyncio.run(_cmd_plugins(config_path, games_dir))
    if command == "stop":
        print("Stop command: send SIGINT/SIGTERM to running process")
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(run_cli())
