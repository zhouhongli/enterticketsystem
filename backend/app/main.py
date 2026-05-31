from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import install_exception_handlers
from app.api.routes import admin, auth, categories, customer, internal
from app.config import get_settings
from app.services.bootstrap import initialize_application


API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        initialize_application(settings)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    install_exception_handlers(app)

    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(categories.router, prefix=API_PREFIX)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.include_router(customer.router, prefix=API_PREFIX)
    app.include_router(internal.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name}

    mount_frontend(app, settings.project_root / "frontend")
    return app


def mount_frontend(app: FastAPI, frontend_root: Path) -> None:
    pages_dir = frontend_root / "pages"
    assets_dir = frontend_root / "assets"

    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    if pages_dir.exists():
        app.mount("/pages", StaticFiles(directory=pages_dir), name="pages")

        @app.get("/", include_in_schema=False)
        async def index() -> FileResponse:
            return FileResponse(pages_dir / "login.html")


app = create_app()
