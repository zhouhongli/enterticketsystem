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


def test_admin_can_create_agent_without_exposing_sensitive_fields(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin01", email="admin01@example.com", role=UserRole.ADMIN
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.post(
                f"{API_PREFIX}/admin/agents",
                json={
                    "username": "agent01",
                    "email": "agent01@example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )

        payload = response.json()
        agent = next(user for user in repo.list_users() if user["username"] == "agent01")

        assert response.status_code == 201
        assert payload == {
            "id": agent["id"],
            "username": "agent01",
            "email": "agent01@example.com",
            "created_at": agent["created_at"],
        }
        assert "password" not in str(payload)
        assert agent["role"] == "agent"
        assert agent["status"] == "active"
        assert agent["password_hash"].startswith("$argon2id$")

    anyio.run(run)


def test_non_admin_cannot_create_agent(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.post(
                f"{API_PREFIX}/admin/agents",
                json={
                    "username": "agent01",
                    "email": "agent01@example.com",
                    "password": "StrongPassword123",
                    "confirm_password": "StrongPassword123",
                },
            )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert all(user["role"] != "agent" for user in repo.list_users())

    anyio.run(run)


def test_admin_lists_only_agents_and_customers_with_safe_fields(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin01", email="admin01@example.com", role=UserRole.ADMIN
    )
    agent, _ = add_user_with_session(
        repo, username="agent01", email="agent01@example.com", role=UserRole.AGENT
    )
    customer, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            agents = await client.get(f"{API_PREFIX}/admin/agents")
            customers = await client.get(f"{API_PREFIX}/admin/customers")

        assert agents.status_code == 200
        assert customers.status_code == 200
        assert agents.json()["items"] == [
            {
                "id": agent["id"],
                "username": "agent01",
                "email": "agent01@example.com",
                "created_at": agent["created_at"],
            }
        ]
        assert customers.json()["items"] == [
            {
                "id": customer["id"],
                "username": "customer01",
                "email": "customer01@example.com",
                "status": "active",
                "created_at": customer["created_at"],
            }
        ]
        assert "password_hash" not in str(agents.json())
        assert "token_hash" not in str(customers.json())

    anyio.run(run)


def test_admin_can_disable_customer_and_revoke_existing_sessions(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin01", email="admin01@example.com", role=UserRole.ADMIN
    )
    customer, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.patch(
                f"{API_PREFIX}/admin/customers/{customer['id']}/status",
                json={"status": "disabled"},
            )

        store = repo.store.read()
        session = next(
            session for session in store["sessions"] if session["user_id"] == customer["id"]
        )
        audit = store["audit_logs"][-1]

        assert response.status_code == 200
        assert response.json()["status"] == "disabled"
        assert session["revoked_at"] is not None
        assert audit["action"] == "customer_status_changed"
        assert SessionService(repo, ttl_hours=8).authenticate(customer_token) is None

    anyio.run(run)


def test_customer_status_errors_are_mapped(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo, username="admin01", email="admin01@example.com", role=UserRole.ADMIN
    )
    agent, _ = add_user_with_session(
        repo, username="agent01", email="agent01@example.com", role=UserRole.AGENT
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            missing = await client.patch(
                f"{API_PREFIX}/admin/customers/missing/status",
                json={"status": "disabled"},
            )
            wrong_role = await client.patch(
                f"{API_PREFIX}/admin/customers/{agent['id']}/status",
                json={"status": "disabled"},
            )

        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert wrong_role.status_code == 409
        assert wrong_role.json()["error"]["code"] == "CONFLICT"

    anyio.run(run)
