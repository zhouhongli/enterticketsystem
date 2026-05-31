from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import customer
from app.config import Settings, get_settings
from app.domain.enums import TicketStatus, UserRole, UserStatus
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


def add_ticket(
    repo: JsonRepository,
    *,
    ticket_id: str,
    title: str,
    description: str,
    category: dict,
    customer_user: dict,
    created_at: str,
    updated_at: str | None = None,
    status: TicketStatus = TicketStatus.UNASSIGNED,
    assignee_user_id: str | None = None,
) -> dict:
    record = {
        "id": ticket_id,
        "title": title,
        "description": description,
        "category_id": category["id"],
        "category_name_snapshot": category["name"],
        "customer_user_id": customer_user["id"],
        "status": status.value,
        "assignee_user_id": assignee_user_id,
        "created_at": created_at,
        "updated_at": updated_at or created_at,
    }

    def save(data: dict) -> dict:
        data["tickets"].append(record)
        return record

    return repo.store.transaction(save)


def assert_message_response_has_no_internal_fields(payload: dict) -> None:
    assert set(payload.keys()) == {
        "id",
        "sender_role",
        "sender_name",
        "content",
        "sent_at",
    }
    serialized = str(payload)
    assert "sender_user_id" not in serialized
    assert "sender_role_snapshot" not in serialized
    assert "sender_name_snapshot" not in serialized
    assert "ticket_id" not in serialized
    assert "email" not in serialized
    assert "customer01@example.com" not in serialized
    assert "agent01@example.com" not in serialized
    assert "audit_logs" not in serialized
    assert "assignee_user_id" not in serialized


def test_customer_can_add_public_message_to_own_open_ticket(tmp_path) -> None:
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
    ticket = add_ticket(
        repo,
        ticket_id="ticket-message-success",
        title="无法正常使用服务",
        description="登录后页面无法继续操作。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
        status=TicketStatus.PROCESSING,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "  请问目前的处理进度如何？  "},
            )
            detail_response = await client.get(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}"
            )

        store = repo.store.read()
        stored_ticket = store["tickets"][0]
        stored_message = store["messages"][0]
        payload = response.json()

        assert response.status_code == 201
        assert payload == {
            "id": stored_message["id"],
            "sender_role": "customer",
            "sender_name": "customer01",
            "content": "请问目前的处理进度如何？",
            "sent_at": stored_message["sent_at"],
        }
        assert_message_response_has_no_internal_fields(payload)

        assert stored_message["ticket_id"] == ticket["id"]
        assert stored_message["sender_user_id"] == customer_user["id"]
        assert stored_message["sender_role_snapshot"] == "customer"
        assert stored_message["sender_name_snapshot"] == "customer01"
        assert stored_message["content"] == "请问目前的处理进度如何？"
        assert isinstance(stored_message["sent_at"], str)

        assert stored_ticket["updated_at"] == stored_message["sent_at"]
        assert stored_ticket["updated_at"] != "2026-05-26T10:20:30Z"
        assert stored_ticket["status"] == "processing"

        assert detail_response.status_code == 200
        detail_payload = detail_response.json()
        assert detail_payload["status"] == "processing"
        assert detail_payload["updated_at"] == stored_message["sent_at"]
        assert detail_payload["messages"] == [payload]

    anyio.run(run)


def test_other_customer_and_missing_ticket_return_404_without_creating_message(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, _ = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    owner, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    _, other_token = add_user_with_session(
        repo,
        username="customer02",
        email="customer02@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-owned-by-customer01",
        title="归属客户一的工单",
        description="其他客户不能留言。",
        category=category,
        customer_user=owner,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, other_token)
            other_customer_response = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "越权留言。"},
            )
            missing_response = await client.post(
                f"{API_PREFIX}/customer/tickets/missing-ticket/messages",
                json={"content": "不存在工单留言。"},
            )

        responses = [other_customer_response, missing_response]
        assert [response.status_code for response in responses] == [404, 404]
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["RESOURCE_NOT_FOUND", "RESOURCE_NOT_FOUND"]
        assert repo.store.read()["messages"] == []

    anyio.run(run)


def test_customer_cannot_add_message_to_closed_ticket(tmp_path) -> None:
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
    ticket = add_ticket(
        repo,
        ticket_id="ticket-closed",
        title="已关闭工单",
        description="关闭后不可新增留言。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T11:20:30Z",
        status=TicketStatus.CLOSED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "关闭后补充。"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert repo.store.read()["messages"] == []
        assert stored_ticket["status"] == "closed"
        assert stored_ticket["updated_at"] == "2026-05-26T11:20:30Z"

    anyio.run(run)


def test_login_required_and_non_customer_roles_cannot_add_message(tmp_path) -> None:
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
    customer_user, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-auth-boundary",
        title="权限边界工单",
        description="仅客户本人可留言。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "未登录留言。"},
            )
            role_responses = []
            for token in (agent_token, admin_token):
                client.cookies.set(settings.session_cookie_name, token)
                role_responses.append(
                    await client.post(
                        f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                        json={"content": "非客户角色留言。"},
                    )
                )

        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert [response.status_code for response in role_responses] == [403, 403]
        assert [
            response.json()["error"]["code"] for response in role_responses
        ] == ["FORBIDDEN", "FORBIDDEN"]
        assert repo.store.read()["messages"] == []

    anyio.run(run)


def test_validation_errors_do_not_create_message_or_update_ticket(tmp_path) -> None:
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
    ticket = add_ticket(
        repo,
        ticket_id="ticket-validation",
        title="留言校验工单",
        description="非法请求不能创建留言。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:30:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            empty_content = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "  "},
            )
            overlong_content = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={"content": "问" * 2001},
            )
            spoofed_fields = await client.post(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}/messages",
                json={
                    "content": "伪造字段留言。",
                    "sender_user_id": "agent01",
                    "sender_role": "agent",
                    "sender_name": "agent01",
                    "sent_at": "2026-05-26T12:00:00Z",
                },
            )

        responses = [empty_content, overlong_content, spoofed_fields]
        stored_ticket = repo.store.read()["tickets"][0]

        assert [response.status_code for response in responses] == [422] * 3
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["VALIDATION_ERROR"] * 3
        assert repo.store.read()["messages"] == []
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["updated_at"] == "2026-05-26T10:30:30Z"

    anyio.run(run)
