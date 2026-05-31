import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import auth
from app.config import Settings, get_settings
from app.domain.enums import UserRole, UserStatus
from app.repositories.json_repository import JsonRepository
from app.security.passwords import PasswordService
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
    app.include_router(auth.router, prefix=API_PREFIX)
    app.dependency_overrides[get_settings] = lambda: settings
    return app


def make_repo(settings: Settings) -> JsonRepository:
    return JsonRepository(JsonFileStore(settings.data_file_path))


def add_user(
    repo: JsonRepository,
    *,
    username: str,
    email: str,
    password: str,
    role: UserRole,
    status: UserStatus = UserStatus.ACTIVE,
) -> dict:
    return repo.add_user(
        username=username,
        email=email,
        password_hash=PasswordService().hash_password(password),
        role=role,
        status=status,
    )


async def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def test_register_creates_active_customer_without_logging_in(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            response = await client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": " customer01 ",
                    "email": "Customer01@Example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )

        payload = response.json()
        user = repo.list_users()[0]

        assert response.status_code == 201
        assert settings.session_cookie_name not in response.headers.get(
            "set-cookie", ""
        )
        assert payload == {
            "id": user["id"],
            "username": "customer01",
            "email": "customer01@example.com",
            "role": "customer",
            "status": "active",
            "created_at": user["created_at"],
        }
        assert user["role"] == "customer"
        assert user["status"] == "active"
        assert user["password_hash"].startswith("$argon2id$")
        assert "password_hash" not in str(payload)

    anyio.run(run)


def test_register_rejects_duplicate_username_or_email(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    add_user(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="StrongPassword123",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            duplicate_username = await client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": " customer01 ",
                    "email": "other@example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )
            duplicate_email = await client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": "customer02",
                    "email": " CUSTOMER01@EXAMPLE.COM ",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )

        assert duplicate_username.status_code == 409
        assert duplicate_email.status_code == 409
        assert duplicate_username.json()["error"]["code"] == "CONFLICT"
        assert duplicate_email.json()["error"]["code"] == "CONFLICT"
        assert len(repo.list_users()) == 1

    anyio.run(run)


def test_register_validation_errors_do_not_create_user(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            password_mismatch = await client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": "customer01",
                    "email": "customer01@example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "AnotherPassword123",
                },
            )
            invalid_username = await client.post(
                f"{API_PREFIX}/auth/register",
                json={
                    "username": "bad name",
                    "email": "customer02@example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )

        assert password_mismatch.status_code == 422
        assert invalid_username.status_code == 422
        assert password_mismatch.json()["error"]["code"] == "VALIDATION_ERROR"
        assert invalid_username.json()["error"]["code"] == "VALIDATION_ERROR"
        assert repo.list_users() == []

    anyio.run(run)


def test_login_accepts_username_or_email_for_all_roles_and_sets_cookie(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    customer = add_user(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="CustomerPassword123",
        role=UserRole.CUSTOMER,
    )
    agent = add_user(
        repo,
        username="agent01",
        email="agent01@example.com",
        password="AgentPassword123",
        role=UserRole.AGENT,
    )
    admin = add_user(
        repo,
        username="admin01",
        email="admin01@example.com",
        password="AdminPassword123",
        role=UserRole.ADMIN,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            customer_login = await client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "identifier": "customer01",
                    "password": "CustomerPassword123",
                },
            )
            agent_login = await client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "identifier": " AGENT01@EXAMPLE.COM ",
                    "password": "AgentPassword123",
                },
            )
            admin_login = await client.post(
                f"{API_PREFIX}/auth/login",
                json={"identifier": "admin01", "password": "AdminPassword123"},
            )

        cookie = customer_login.headers["set-cookie"]

        assert customer_login.status_code == 200
        assert agent_login.status_code == 200
        assert admin_login.status_code == 200
        assert customer_login.json() == {
            "id": customer["id"],
            "username": "customer01",
            "email": "customer01@example.com",
            "role": "customer",
            "status": "active",
        }
        assert agent_login.json()["id"] == agent["id"]
        assert agent_login.json()["role"] == "agent"
        assert admin_login.json()["id"] == admin["id"]
        assert admin_login.json()["role"] == "admin"
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Path=/" in cookie
        assert "Max-Age=28800" in cookie
        assert "token_hash" not in str(customer_login.json())
        assert customer_login.cookies.get(settings.session_cookie_name) not in str(
            repo.store.read()
        )

    anyio.run(run)


def test_login_failure_uses_single_error_without_creating_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    add_user(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="StrongPassword123",
        role=UserRole.CUSTOMER,
    )
    add_user(
        repo,
        username="disabled01",
        email="disabled01@example.com",
        password="StrongPassword123",
        role=UserRole.CUSTOMER,
        status=UserStatus.DISABLED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            missing = await client.post(
                f"{API_PREFIX}/auth/login",
                json={"identifier": "missing", "password": "StrongPassword123"},
            )
            wrong_password = await client.post(
                f"{API_PREFIX}/auth/login",
                json={"identifier": "customer01", "password": "wrong-password"},
            )
            disabled = await client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "identifier": "disabled01",
                    "password": "StrongPassword123",
                },
            )

        for response in (missing, wrong_password, disabled):
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "LOGIN_FAILED"
            assert response.json()["error"]["message"] == "账号或密码错误，或账号不可用。"
        assert repo.store.read()["sessions"] == []

    anyio.run(run)


def test_me_and_logout_require_and_revoke_current_session(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    add_user(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="StrongPassword123",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            login = await client.post(
                f"{API_PREFIX}/auth/login",
                json={
                    "identifier": "customer01",
                    "password": "StrongPassword123",
                },
            )
            me = await client.get(f"{API_PREFIX}/auth/me")
            logout = await client.post(f"{API_PREFIX}/auth/logout")
            after_logout = await client.get(f"{API_PREFIX}/auth/me")

        session = repo.store.read()["sessions"][0]

        assert login.status_code == 200
        assert me.status_code == 200
        assert me.json()["username"] == "customer01"
        assert logout.status_code == 200
        assert logout.json() == {"success": True}
        assert "Max-Age=0" in logout.headers["set-cookie"]
        assert session["revoked_at"] is not None
        assert after_logout.status_code == 401
        assert after_logout.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"

    anyio.run(run)


def test_me_rejects_disabled_user_session_and_clears_cookie(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    user = add_user(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="StrongPassword123",
        role=UserRole.CUSTOMER,
    )
    token = SessionService(repo, ttl_hours=8).create_session(user["id"]).raw_token
    repo.update_user_status(user["id"], UserStatus.DISABLED)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, token)
            response = await client.get(f"{API_PREFIX}/auth/me")

        session = repo.store.read()["sessions"][0]

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert "Max-Age=0" in response.headers["set-cookie"]
        assert session["revoked_at"] is not None

    anyio.run(run)
