"""FastAPI backend for the UGAF web UI.

Every route is a thin wrapper around :class:`~ugaf.webapp.session.AppSession`,
which itself only delegates to existing UGAF managers — no automation
logic lives in this file.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ugaf.webapp.session import AppSession

__all__ = [
    "create_app",
]

_STATIC_DIR = Path(__file__).parent / "static"


class TapRequest(BaseModel):
    """Request body for a tap action."""

    x: int
    y: int


class SwipeRequest(BaseModel):
    """Request body for a swipe/drag action."""

    x1: int
    y1: int
    x2: int
    y2: int
    duration: float = 0.3


class TextRequest(BaseModel):
    """Request body for a type-text action."""

    text: str


def create_app(
    config_path: Path | str | None = None,
    games_dir: Path | str | None = None,
) -> FastAPI:
    """Build the FastAPI application, wiring startup/shutdown to an AppSession.

    Args:
        config_path: Forwarded to :class:`~ugaf.core.bootstrap.Application`.
        games_dir: Forwarded to :class:`~ugaf.core.bootstrap.Application`.

    Returns:
        A configured :class:`fastapi.FastAPI` instance.

    """
    session = AppSession(config_path=config_path, games_dir=games_dir)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await session.start()
        try:
            yield
        finally:
            await session.stop()

    app = FastAPI(title="UGAF Control Panel", lifespan=_lifespan)
    app.state.session = session

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return (_STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.get("/api/devices")
    async def list_devices() -> list[dict[str, Any]]:
        devices = session.list_devices()
        return [
            {
                "id": d.id,
                "name": d.name,
                "status": d.status.value,
                "platform": d.platform,
                "transport": d.transport,
                "connected": session.is_connected(d.id),
            }
            for d in devices
        ]

    @app.post("/api/devices/{device_id}/connect")
    async def connect_device(device_id: str) -> dict[str, Any]:
        try:
            session.connect_device(device_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"connected": True, "device_id": device_id}

    @app.post("/api/devices/{device_id}/disconnect")
    async def disconnect_device(device_id: str) -> dict[str, Any]:
        session.disconnect_device(device_id)
        return {"connected": False, "device_id": device_id}

    @app.get("/api/devices/{device_id}/screenshot")
    async def screenshot(device_id: str) -> StreamingResponse:
        try:
            image = session.capture(device_id)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        png_bytes = session.encode_png(image)
        return StreamingResponse(io.BytesIO(png_bytes), media_type="image/png")

    @app.post("/api/devices/{device_id}/tap")
    async def tap(device_id: str, body: TapRequest) -> dict[str, Any]:
        try:
            session.tap(device_id, body.x, body.y)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"tapped": [body.x, body.y]}

    @app.post("/api/devices/{device_id}/swipe")
    async def swipe(device_id: str, body: SwipeRequest) -> dict[str, Any]:
        try:
            session.swipe(device_id, body.x1, body.y1, body.x2, body.y2, body.duration)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"swiped": True}

    @app.post("/api/devices/{device_id}/text")
    async def type_text(device_id: str, body: TextRequest) -> dict[str, Any]:
        try:
            session.type_text(device_id, body.text)
        except KeyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"typed": body.text}

    @app.get("/api/plugins")
    async def list_plugins() -> list[dict[str, Any]]:
        return session.list_plugins()

    @app.post("/api/plugins/{plugin_id}/run")
    async def run_plugin(plugin_id: str) -> dict[str, Any]:
        try:
            await session.run_plugin(plugin_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"running": plugin_id}

    @app.post("/api/plugins/{plugin_id}/stop")
    async def stop_plugin(plugin_id: str) -> dict[str, Any]:
        try:
            await session.stop_plugin(plugin_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"stopped": plugin_id}

    @app.get("/api/plugins/{plugin_id}/health")
    async def plugin_health(plugin_id: str) -> dict[str, Any]:
        try:
            return await session.plugin_health(plugin_id)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/logs")
    async def logs(since: int = 0) -> list[dict[str, Any]]:
        entries = list(session.log_buffer)
        return entries[since:]

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
