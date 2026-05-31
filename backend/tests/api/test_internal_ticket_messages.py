from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import internal
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
    app.include_router(internal.router, prefix=API_PREFIX)
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


def messages(repo: JsonRepository) -> list[dict]:
    return repo.store.read()["messages"]


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
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert "assignee_user_id" not in serialized
    assert "audit_logs" not in serialized


def test_responsible_agent_adds_internal_public_message_without_status_change(
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
    agent, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    customer, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-agent-message",
        title="处理中工单",
        description="客服可回复。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:30:30Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, agent_token)
            response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "  我们正在核查该问题，请稍候。  "},
            )
            detail_response = await client.get(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}"
            )

        stored_ticket = repo.store.read()["tickets"][0]
        stored_message = messages(repo)[0]
        payload = response.json()

        assert response.status_code == 201
        assert payload == {
            "id": stored_message["id"],
            "sender_role": "agent",
            "sender_name": "agent01",
            "content": "我们正在核查该问题，请稍候。",
            "sent_at": stored_message["sent_at"],
        }
        assert_message_response_has_no_internal_fields(payload)
        assert stored_message["ticket_id"] == ticket["id"]
        assert stored_message["sender_user_id"] == agent["id"]
        assert stored_message["sender_role_snapshot"] == "agent"
        assert stored_message["sender_name_snapshot"] == "agent01"
        assert stored_ticket["status"] == "processing"
        assert stored_ticket["updated_at"] == stored_message["sent_at"]
        assert stored_ticket["updated_at"] != "2026-05-26T10:30:30Z"
        assert detail_response.status_code == 200
        assert detail_response.json()["messages"] == [payload]

    anyio.run(run)


def test_admin_can_add_message_to_unassigned_open_ticket(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    customer, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-admin-message",
        title="待分配工单",
        description="管理员可直接留言。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        status=TicketStatus.UNASSIGNED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "管理员先记录处理意见。"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        payload = response.json()

        assert response.status_code == 201
        assert payload["sender_role"] == "admin"
        assert payload["sender_name"] == "admin01"
        assert payload["content"] == "管理员先记录处理意见。"
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["assignee_user_id"] is None
        assert stored_ticket["updated_at"] == payload["sent_at"]
        assert_message_response_has_no_internal_fields(payload)

    anyio.run(run)


def test_non_responsible_agent_customer_and_anonymous_cannot_add_internal_message(
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
    responsible_agent, _ = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    other_agent, other_agent_token = add_user_with_session(
        repo,
        username="agent02",
        email="agent02@example.com",
        role=UserRole.AGENT,
    )
    customer, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-message-permission",
        title="权限边界工单",
        description="非负责人不能留言。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=responsible_agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "未登录留言。"},
            )
            client.cookies.set(settings.session_cookie_name, other_agent_token)
            other_agent_response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "非负责人留言。"},
            )
            client.cookies.set(settings.session_cookie_name, customer_token)
            customer_response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "客户不能走内部接口。"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert other_agent_response.status_code == 403
        assert other_agent_response.json()["error"]["code"] == "FORBIDDEN"
        assert customer_response.status_code == 403
        assert customer_response.json()["error"]["code"] == "FORBIDDEN"
        assert messages(repo) == []
        assert stored_ticket["updated_at"] == "2026-05-26T10:20:30Z"

    anyio.run(run)


def test_missing_or_closed_ticket_rejects_internal_message_without_changes(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    customer, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-closed-message",
        title="已关闭工单",
        description="关闭后不能新增留言。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T11:20:30Z",
        status=TicketStatus.CLOSED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            missing_response = await client.post(
                f"{API_PREFIX}/internal/tickets/missing-ticket/messages",
                json={"content": "不存在工单留言。"},
            )
            closed_response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "关闭后留言。"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        assert missing_response.status_code == 404
        assert missing_response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert closed_response.status_code == 409
        assert closed_response.json()["error"]["code"] == "CONFLICT"
        assert messages(repo) == []
        assert stored_ticket["status"] == "closed"
        assert stored_ticket["updated_at"] == "2026-05-26T11:20:30Z"

    anyio.run(run)


def test_internal_message_validation_errors_do_not_create_message_or_update_ticket(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    customer, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-message-validation",
        title="留言校验工单",
        description="非法请求不能创建留言。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:30:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            missing_content = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={},
            )
            empty_content = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "  "},
            )
            overlong_content = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "问" * 2001},
            )
            spoofed_fields = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={
                    "content": "伪造字段留言。",
                    "sender_user_id": "agent01",
                    "sender_role": "agent",
                    "sent_at": "2026-05-26T12:00:00Z",
                },
            )

        responses = [missing_content, empty_content, overlong_content, spoofed_fields]
        stored_ticket = repo.store.read()["tickets"][0]
        assert [response.status_code for response in responses] == [422] * 4
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["VALIDATION_ERROR"] * 4
        assert messages(repo) == []
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["updated_at"] == "2026-05-26T10:30:30Z"

    anyio.run(run)
