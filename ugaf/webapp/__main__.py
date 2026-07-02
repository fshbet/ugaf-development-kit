"""Launch the UGAF web control panel: ``python -m ugaf.webapp``."""

from __future__ import annotations

import argparse

import uvicorn

from ugaf.webapp.server import create_app


def main() -> None:
    """Parse CLI args and run the web control panel with uvicorn."""
    parser = argparse.ArgumentParser(prog="ugaf.webapp")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8420)
    parser.add_argument("--config", default="config/default.yaml")
    parser.add_argument("--games-dir", default="games")
    args = parser.parse_args()

    app = create_app(config_path=args.config, games_dir=args.games_dir)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
