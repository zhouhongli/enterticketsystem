import anyio
import httpx
from fastapi import Depends, FastAPI

from app.api.dependencies import require_admin
from app.api.errors import install_exception_handlers
from app.config import Settings, get_settings
from app.domain.enums import UserRole, UserStatus
from app.repositories.json_repository import JsonRepository
from app.security.sessions import SessionService
from app.storage.json_store import JsonFileStore


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
    app.dependency_overrides[get_settings] = lambda: settings

    @app.get("/admin-only")
    async def admin_only(current_user=Depends(require_admin)):
        return {"id": current_user["id"], "role": current_user["role"]}

    return app


def make_repo(settings: Settings) -> JsonRepository:
    return JsonRepository(JsonFileStore(settings.data_file_path))


def create_user_session(
    repo: JsonRepository,
    *,
    username: str,
    email: str,
    role: UserRole,
    status: UserStatus = UserStatus.ACTIVE,
) -> str:
    user = repo.add_user(
        username=username,
        email=email,
        password_hash="hash",
        role=role,
        status=status,
    )
    return SessionService(repo, ttl_hours=8).create_session(user["id"]).raw_token


def test_admin_dependency_requires_valid_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    app = make_app(settings)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get("/admin-only")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    anyio.run(run)


def test_admin_dependency_rejects_non_admin_user(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    token = create_user_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = await client.get("/admin-only")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"

    anyio.run(run)


def test_admin_dependency_accepts_active_admin_user(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    token = create_user_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    app = make_app(settings)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = await client.get("/admin-only")

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    anyio.run(run)


def test_admin_dependency_rejects_disabled_user_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    token = create_user_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
        status=UserStatus.DISABLED,
    )
    app = make_app(settings)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = await client.get("/admin-only")

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    anyio.run(run)
