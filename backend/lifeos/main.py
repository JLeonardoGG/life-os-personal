from __future__ import annotations

import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from lifeos import __version__
from lifeos.config import Settings, get_settings
from lifeos.database import Database
from lifeos.migrations import upgrade_database
from lifeos.routers import automation, data, finance, life, system, tax
from lifeos.services.backups import ensure_daily_backup


def _frontend_file(settings: Settings, name: str) -> FileResponse:
    path = (settings.project_root / name).resolve()
    if path.parent != settings.project_root.resolve() or not path.exists():
        raise HTTPException(status_code=404, detail="Frontend file not found")
    response = FileResponse(path)
    if path.suffix == ".html":
        response.headers["Cache-Control"] = "no-store"
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        os.umask(0o077)
        upgrade_database(app_settings)
        app.state.database = Database(app_settings.database_path)
        with app.state.database.session() as session:
            ensure_daily_backup(session, app_settings)
        yield
        app.state.database.engine.dispose()

    app = FastAPI(
        title="Life OS Local API",
        version=__version__,
        description="Local-only API for Life OS Personal.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = app_settings
    app.include_router(system.router)
    app.include_router(finance.router)
    app.include_router(life.router)
    app.include_router(tax.router)
    app.include_router(data.router)
    app.include_router(automation.router)
    app.mount(
        "/frontend",
        StaticFiles(directory=app_settings.project_root / "frontend"),
        name="frontend",
    )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return _frontend_file(app_settings, "index.html")

    @app.get("/index.html", include_in_schema=False)
    def index_html() -> FileResponse:
        return _frontend_file(app_settings, "index.html")

    @app.get("/lifeos_dashboard.html", include_in_schema=False)
    def dashboard_html() -> FileResponse:
        return _frontend_file(app_settings, "lifeos_dashboard.html")

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return _frontend_file(app_settings, "manifest.webmanifest")

    @app.get("/sw.js", include_in_schema=False)
    def service_worker() -> FileResponse:
        return _frontend_file(app_settings, "sw.js")

    @app.get("/lifeos-icon.svg", include_in_schema=False)
    def icon() -> FileResponse:
        return _frontend_file(app_settings, "lifeos-icon.svg")

    return app


app = create_app()


def run() -> None:
    settings = get_settings()
    if settings.host not in {"127.0.0.1", "::1", "localhost"}:
        raise RuntimeError("Life OS V1 only permits local loopback binding")
    uvicorn.run("lifeos.main:app", host=settings.host, port=settings.port, reload=False)
