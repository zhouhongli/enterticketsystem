from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import admin
from app.config import Settings, get_settings
from app.domain.enums import UserRole
from app.repositories.json_repository import JsonRepository
from app.security.sessions import SessionService
from app.storage.json_store import JsonFileStore


API_PREFIX = "/api/v1"


def make_settings(tmp_path) -> Settings:
    return Settings(
        app_name="test",
        app_env="test",
        project_root=tmp_path,
        backend_root=tmp_path,
        data_file_path=tmp_path / "store.json",
        session_cookie_name="ticket_session",
        session_cookie_secure=False,
        session_ttl_hours=8,
        initial_admin_username="",
        initial_admin_email="",
        initial_admin_password="",
    )


def make_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_exception_handlers(app)
    app.include_router(admin.router, prefix=API_PREFIX)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def make_repo(settings: Settings) -> JsonRepository:
    return JsonRepository(JsonFileStore(settings.data_file_path))


def add_user_with_session(
    repo: JsonRepository,
    *,
    username: str,
    email: str,
    role: UserRole,
) -> tuple[dict, str]:
    user = repo.add_user(
        username=username,
        email=email,
        password_hash="hash",
        role=role,
    )
    token = SessionService(repo, ttl_hours=8).create_session(user["id"]).raw_token
    return user, token


async def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def test_admin_can_get_stats(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin", email="a@b.com", role=UserRole.ADMIN
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.get(f"{API_PREFIX}/admin/stats?range=7d")

        assert response.status_code == 200
        data = response.json()
        assert "overview" in data
        assert "trend" in data
        assert "avg_times" in data
        assert "category_dist" in data
        assert "agent_workload" in data
        assert "recent_logs" in data

    anyio.run(run)


def test_non_admin_cannot_get_stats(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, customer_token = add_user_with_session(
        repo, username="cust01", email="c@b.com", role=UserRole.CUSTOMER
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.get(f"{API_PREFIX}/admin/stats?range=7d")

        assert response.status_code == 403

    anyio.run(run)


def test_unauthenticated_cannot_get_stats(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            response = await client.get(f"{API_PREFIX}/admin/stats?range=7d")

        assert response.status_code == 401

    anyio.run(run)


def test_invalid_range_returns_422(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin", email="a@b.com", role=UserRole.ADMIN
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.get(f"{API_PREFIX}/admin/stats?range=invalid")

        assert response.status_code == 422

    anyio.run(run)
