from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api import alerts, auth, dashboard, export, health, reports, transactions
from backend.app.core.config import get_settings
from backend.app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (health, auth, dashboard, transactions, alerts, reports, export):
        app.include_router(module.router, prefix="/api")

    @app.get("/", include_in_schema=False)
    def index():
        return RedirectResponse(url="/alerts.html")

    if settings.frontend_dir.exists():
        app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")

    return app


app = create_app()
