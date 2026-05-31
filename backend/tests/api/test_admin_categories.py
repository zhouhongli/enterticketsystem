from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import categories
from app.config import Settings, get_settings
from app.domain.enums import CategoryStatus, UserRole
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
    app.include_router(categories.router, prefix=API_PREFIX)
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


def test_admin_can_create_list_edit_and_toggle_categories(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            created = await client.post(
                f"{API_PREFIX}/admin/categories",
                json={"name": "  产品故障  "},
            )
            listed = await client.get(f"{API_PREFIX}/admin/categories")
            category_id = created.json()["id"]
            renamed = await client.patch(
                f"{API_PREFIX}/admin/categories/{category_id}",
                json={"name": "产品使用问题"},
            )
            disabled = await client.patch(
                f"{API_PREFIX}/admin/categories/{category_id}/status",
                json={"status": "inactive"},
            )
            enabled = await client.patch(
                f"{API_PREFIX}/admin/categories/{category_id}/status",
                json={"status": "active"},
            )

        category = repo.get_category(category_id)
        audit_actions = [record["action"] for record in repo.store.read()["audit_logs"]]

        assert created.status_code == 201
        assert created.json() == {
            "id": category_id,
            "name": "产品故障",
            "status": "active",
            "created_at": category["created_at"],
            "updated_at": category["created_at"],
        }
        assert listed.status_code == 200
        assert listed.json()["items"] == [created.json()]
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "产品使用问题"
        assert disabled.status_code == 200
        assert disabled.json()["status"] == "inactive"
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "active"
        assert "created_by_user_id" not in str(enabled.json())
        assert audit_actions == [
            "category_created",
            "category_updated",
            "category_status_changed",
            "category_status_changed",
        ]

    anyio.run(run)


def test_customer_active_categories_return_only_active_safe_fields(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, _ = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    _, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    active = repo.create_category(name="产品故障", actor_user=admin)
    inactive = repo.create_category(name="历史咨询", actor_user=admin)
    repo.update_category_status(
        category_id=inactive["id"],
        status=CategoryStatus.INACTIVE,
        actor_user=admin,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.get(f"{API_PREFIX}/categories/active")

        assert response.status_code == 200
        assert response.json() == {
            "items": [{"id": active["id"], "name": "产品故障"}]
        }
        assert "status" not in str(response.json())
        assert "created_by_user_id" not in str(response.json())

    anyio.run(run)


def test_non_admin_users_cannot_manage_categories(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    _, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            responses = []
            for token in (customer_token, agent_token):
                client.cookies.set(settings.session_cookie_name, token)
                responses.append(
                    await client.post(
                        f"{API_PREFIX}/admin/categories",
                        json={"name": "产品故障"},
                    )
                )

        assert [response.status_code for response in responses] == [403, 403]
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["FORBIDDEN", "FORBIDDEN"]
        assert repo.list_categories() == []

    anyio.run(run)


def test_duplicate_category_name_returns_conflict(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    repo.create_category(name="产品故障", actor_user=admin)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.post(
                f"{API_PREFIX}/admin/categories",
                json={"name": "产品故障"},
            )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert len(repo.list_categories()) == 1

    anyio.run(run)


def test_category_errors_are_mapped(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            validation = await client.post(
                f"{API_PREFIX}/admin/categories",
                json={"name": " "},
            )
            missing = await client.patch(
                f"{API_PREFIX}/admin/categories/missing",
                json={"name": "产品故障"},
            )
            missing_status = await client.patch(
                f"{API_PREFIX}/admin/categories/missing/status",
                json={"status": "inactive"},
            )
            invalid_status = await client.patch(
                f"{API_PREFIX}/admin/categories/missing/status",
                json={"status": "archived"},
            )

        assert validation.status_code == 422
        assert validation.json()["error"]["code"] == "VALIDATION_ERROR"
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert missing_status.status_code == 404
        assert missing_status.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert invalid_status.status_code == 422
        assert invalid_status.json()["error"]["code"] == "VALIDATION_ERROR"

    anyio.run(run)
