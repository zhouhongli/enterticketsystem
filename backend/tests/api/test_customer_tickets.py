from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import customer
from app.config import Settings, get_settings
from app.domain.enums import CategoryStatus, UserRole, UserStatus
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
    app.include_router(customer.router, prefix=API_PREFIX)
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
    status: UserStatus = UserStatus.ACTIVE,
) -> tuple[dict, str]:
    user = repo.add_user(
        username=username,
        email=email,
        password_hash="hash",
        role=role,
        status=status,
    )
    token = SessionService(repo, ttl_hours=8).create_session(user["id"]).raw_token
    return user, token


async def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def test_active_customer_can_create_ticket_with_snapshot_and_audit_log(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, _ = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    customer_user, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "title": "  无法正常使用服务  ",
                    "description": "  登录后页面无法继续操作。  ",
                },
            )

        store = repo.store.read()
        ticket = store["tickets"][0]
        ticket_audit_logs = [
            record
            for record in store["audit_logs"]
            if record["target_type"] == "ticket"
        ]
        payload = response.json()

        assert response.status_code == 201
        assert payload == {
            "id": ticket["id"],
            "title": "无法正常使用服务",
            "description": "登录后页面无法继续操作。",
            "category_name": "产品故障",
            "status": "unassigned",
            "created_at": ticket["created_at"],
            "updated_at": ticket["updated_at"],
            "messages": [],
        }
        assert ticket["customer_user_id"] == customer_user["id"]
        assert ticket["category_id"] == category["id"]
        assert ticket["category_name_snapshot"] == "产品故障"
        assert ticket["status"] == "unassigned"
        assert ticket["assignee_user_id"] is None
        assert ticket_audit_logs == [
            {
                "id": ticket_audit_logs[0]["id"],
                "action": "ticket_created",
                "actor_user_id": customer_user["id"],
                "actor_role_snapshot": "customer",
                "target_type": "ticket",
                "target_id": ticket["id"],
                "ticket_id": ticket["id"],
                "changes": {"status": {"before": None, "after": "unassigned"}},
                "occurred_at": ticket_audit_logs[0]["occurred_at"],
            }
        ]
        assert "assignee" not in str(payload)
        assert "assignee_user_id" not in str(payload)
        assert "audit_logs" not in str(payload)
        assert "customer" not in str(payload)
        assert "customer01@example.com" not in str(payload)

    anyio.run(run)


def test_ticket_keeps_category_name_snapshot_after_category_rename(tmp_path) -> None:
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
    category = repo.create_category(name="产品故障", actor_user=admin)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "title": "无法正常使用服务",
                    "description": "登录后页面无法继续操作。",
                },
            )

        repo.update_category_name(
            category_id=category["id"],
            name="产品使用问题",
            actor_user=admin,
        )
        ticket = repo.store.read()["tickets"][0]

        assert response.status_code == 201
        assert response.json()["category_name"] == "产品故障"
        assert ticket["category_name_snapshot"] == "产品故障"
        assert repo.get_category(category["id"])["name"] == "产品使用问题"

    anyio.run(run)


def test_login_required_and_non_customer_roles_cannot_create_ticket(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    _, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    app = make_app(settings)
    request_body = {
        "category_id": category["id"],
        "title": "无法正常使用服务",
        "description": "登录后页面无法继续操作。",
    }

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json=request_body,
            )
            role_responses = []
            for token in (agent_token, admin_token):
                client.cookies.set(settings.session_cookie_name, token)
                role_responses.append(
                    await client.post(
                        f"{API_PREFIX}/customer/tickets",
                        json=request_body,
                    )
                )

        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert [response.status_code for response in role_responses] == [403, 403]
        assert [
            response.json()["error"]["code"] for response in role_responses
        ] == ["FORBIDDEN", "FORBIDDEN"]
        assert repo.store.read()["tickets"] == []

    anyio.run(run)


def test_inactive_or_missing_category_cannot_create_ticket(tmp_path) -> None:
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
            inactive_response = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": inactive["id"],
                    "title": "无法正常使用服务",
                    "description": "登录后页面无法继续操作。",
                },
            )
            missing_response = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": "missing-category",
                    "title": "无法正常使用服务",
                    "description": "登录后页面无法继续操作。",
                },
            )

        assert inactive_response.status_code == 409
        assert missing_response.status_code == 409
        assert inactive_response.json()["error"]["code"] == "CONFLICT"
        assert missing_response.json()["error"]["code"] == "CONFLICT"
        assert repo.store.read()["tickets"] == []

    anyio.run(run)


def test_validation_errors_do_not_create_ticket(tmp_path) -> None:
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
    category = repo.create_category(name="产品故障", actor_user=admin)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            missing_title = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "description": "登录后页面无法继续操作。",
                },
            )
            empty_description = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "title": "无法正常使用服务",
                    "description": "  ",
                },
            )
            overlong_title = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "title": "问" * 101,
                    "description": "登录后页面无法继续操作。",
                },
            )
            spoofed_fields = await client.post(
                f"{API_PREFIX}/customer/tickets",
                json={
                    "category_id": category["id"],
                    "title": "无法正常使用服务",
                    "description": "登录后页面无法继续操作。",
                    "status": "processing",
                    "assignee_user_id": "agent01",
                    "customer_user_id": "other-customer",
                },
            )

        responses = [
            missing_title,
            empty_description,
            overlong_title,
            spoofed_fields,
        ]
        assert [response.status_code for response in responses] == [422] * 4
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["VALIDATION_ERROR"] * 4
        assert repo.store.read()["tickets"] == []

    anyio.run(run)
