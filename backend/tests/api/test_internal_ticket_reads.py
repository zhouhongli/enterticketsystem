from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import internal
from app.config import Settings, get_settings
from app.domain.enums import AuditAction, TicketStatus, UserRole, UserStatus
from app.domain.models import audit_log_record
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
        data["audit_logs"].append(
            audit_log_record(
                action=AuditAction.TICKET_CREATED,
                actor_user=customer_user,
                target_type="ticket",
                target_id=ticket_id,
                ticket_id=ticket_id,
                changes={"status": {"before": None, "after": status.value}},
                now=created_at,
            )
        )
        return record

    return repo.store.transaction(save)


def add_message(
    repo: JsonRepository,
    *,
    message_id: str,
    ticket_id: str,
    sender_user: dict,
    content: str,
    sent_at: str,
) -> dict:
    record = {
        "id": message_id,
        "ticket_id": ticket_id,
        "sender_user_id": sender_user["id"],
        "sender_role_snapshot": sender_user["role"],
        "sender_name_snapshot": sender_user["username"],
        "content": content,
        "sent_at": sent_at,
    }

    def save(data: dict) -> dict:
        data["messages"].append(record)
        return record

    return repo.store.transaction(save)


def assert_internal_payload_has_no_sensitive_fields(payload: dict) -> None:
    serialized = str(payload)
    assert "customer01@example.com" not in serialized
    assert "customer02@example.com" not in serialized
    assert "agent01@example.com" not in serialized
    assert "admin01@example.com" not in serialized
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert "customer_user_id" not in serialized
    assert "assignee_user_id" not in serialized
    assert "actor_user_id" not in serialized


def test_agent_and_admin_can_list_all_tickets_with_single_status_filter(
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
    agent, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    customer01, _ = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    customer02, _ = add_user_with_session(
        repo,
        username="customer02",
        email="customer02@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    older = add_ticket(
        repo,
        ticket_id="ticket-older",
        title="较早待分配工单",
        description="等待内部处理。",
        category=category,
        customer_user=customer01,
        created_at="2026-05-26T10:20:30Z",
        status=TicketStatus.UNASSIGNED,
    )
    newer = add_ticket(
        repo,
        ticket_id="ticket-newer",
        title="较新处理中工单",
        description="已分配给客服。",
        category=category,
        customer_user=customer02,
        created_at="2026-05-27T10:20:30Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, agent_token)
            agent_list = await client.get(f"{API_PREFIX}/internal/tickets")
            filtered = await client.get(
                f"{API_PREFIX}/internal/tickets?status=processing"
            )
            client.cookies.set(settings.session_cookie_name, admin_token)
            admin_list = await client.get(f"{API_PREFIX}/internal/tickets")

        agent_payload = agent_list.json()
        filtered_payload = filtered.json()
        admin_payload = admin_list.json()

        assert agent_list.status_code == 200
        assert admin_list.status_code == 200
        assert agent_payload == admin_payload
        assert agent_payload == {
            "items": [
                {
                    "id": newer["id"],
                    "title": "较新处理中工单",
                    "customer": {"id": customer02["id"], "username": "customer02"},
                    "category_name": "产品故障",
                    "status": "processing",
                    "assignee": {"id": agent["id"], "username": "agent01"},
                    "created_at": "2026-05-27T10:20:30Z",
                },
                {
                    "id": older["id"],
                    "title": "较早待分配工单",
                    "customer": {"id": customer01["id"], "username": "customer01"},
                    "category_name": "产品故障",
                    "status": "unassigned",
                    "assignee": None,
                    "created_at": "2026-05-26T10:20:30Z",
                },
            ]
        }
        assert filtered.status_code == 200
        assert filtered_payload == {"items": [agent_payload["items"][0]]}
        assert_internal_payload_has_no_sensitive_fields(agent_payload)
        assert_internal_payload_has_no_sensitive_fields(filtered_payload)

    anyio.run(run)


def test_internal_detail_returns_messages_and_ticket_audit_logs_in_required_order(
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
    agent, _ = add_user_with_session(
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
        ticket_id="ticket-detail",
        title="无法正常使用服务",
        description="登录后页面无法继续操作。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:24:00Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=agent["id"],
    )
    add_message(
        repo,
        message_id="message-2",
        ticket_id=ticket["id"],
        sender_user=agent,
        content="我们正在处理。",
        sent_at="2026-05-26T10:23:00Z",
    )
    add_message(
        repo,
        message_id="message-1",
        ticket_id=ticket["id"],
        sender_user=customer,
        content="请协助处理。",
        sent_at="2026-05-26T10:22:00Z",
    )

    def add_audit_logs(data: dict) -> None:
        data["audit_logs"].append(
            audit_log_record(
                action=AuditAction.TICKET_STATUS_CHANGED,
                actor_user=agent,
                target_type="ticket",
                target_id=ticket["id"],
                ticket_id=ticket["id"],
                changes={"status": {"before": "unassigned", "after": "processing"}},
                now="2026-05-26T10:24:00Z",
            )
        )
        data["audit_logs"].append(
            audit_log_record(
                action=AuditAction.CATEGORY_UPDATED,
                actor_user=admin,
                target_type="category",
                target_id=category["id"],
                changes={"name": {"before": "产品故障", "after": "产品使用问题"}},
                now="2026-05-26T10:25:00Z",
            )
        )

    repo.store.transaction(add_audit_logs)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.get(f"{API_PREFIX}/internal/tickets/{ticket['id']}")

        payload = response.json()

        assert response.status_code == 200
        assert payload == {
            "id": ticket["id"],
            "title": "无法正常使用服务",
            "description": "登录后页面无法继续操作。",
            "category_name": "产品故障",
            "customer": {"id": customer["id"], "username": "customer01"},
            "status": "processing",
            "assignee": {"id": agent["id"], "username": "agent01"},
            "created_at": "2026-05-26T10:20:30Z",
            "updated_at": "2026-05-26T10:24:00Z",
            "messages": [
                {
                    "id": "message-1",
                    "sender_role": "customer",
                    "sender_name": "customer01",
                    "content": "请协助处理。",
                    "sent_at": "2026-05-26T10:22:00Z",
                },
                {
                    "id": "message-2",
                    "sender_role": "agent",
                    "sender_name": "agent01",
                    "content": "我们正在处理。",
                    "sent_at": "2026-05-26T10:23:00Z",
                },
            ],
            "audit_logs": [
                {
                    "id": payload["audit_logs"][0]["id"],
                    "action": "ticket_status_changed",
                    "actor": {
                        "id": agent["id"],
                        "role": "agent",
                        "username": "agent01",
                    },
                    "changes": {
                        "status": {"before": "unassigned", "after": "processing"}
                    },
                    "occurred_at": "2026-05-26T10:24:00Z",
                },
                {
                    "id": payload["audit_logs"][1]["id"],
                    "action": "ticket_created",
                    "actor": {
                        "id": customer["id"],
                        "role": "customer",
                        "username": "customer01",
                    },
                    "changes": {"status": {"before": None, "after": "processing"}},
                    "occurred_at": "2026-05-26T10:20:30Z",
                },
            ],
        }
        assert "category_updated" not in str(payload)
        assert_internal_payload_has_no_sensitive_fields(payload)

    anyio.run(run)


def test_missing_internal_ticket_returns_404_without_resource_content(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, agent_token)
            response = await client.get(f"{API_PREFIX}/internal/tickets/missing")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        assert "missing" not in str(response.json())

    anyio.run(run)


def test_internal_ticket_list_rejects_invalid_or_unsupported_query_params(
    tmp_path,
) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    _, agent_token = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, agent_token)
            invalid_status = await client.get(
                f"{API_PREFIX}/internal/tickets?status=invalid"
            )
            unsupported = await client.get(
                f"{API_PREFIX}/internal/tickets?customer=customer01"
            )
            repeated = await client.get(
                f"{API_PREFIX}/internal/tickets?status=processing&status=closed"
            )

        responses = [invalid_status, unsupported, repeated]
        assert [response.status_code for response in responses] == [422] * 3
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["VALIDATION_ERROR"] * 3

    anyio.run(run)


def test_login_required_and_customer_cannot_read_internal_tickets(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    customer, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    admin, _ = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        role=UserRole.ADMIN,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-auth-boundary",
        title="内部权限边界工单",
        description="客户不能读取内部接口。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous_list = await client.get(f"{API_PREFIX}/internal/tickets")
            anonymous_detail = await client.get(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}"
            )
            client.cookies.set(settings.session_cookie_name, customer_token)
            customer_list = await client.get(f"{API_PREFIX}/internal/tickets")
            customer_detail = await client.get(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}"
            )

        assert anonymous_list.status_code == 401
        assert anonymous_detail.status_code == 401
        assert anonymous_list.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert anonymous_detail.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert customer_list.status_code == 403
        assert customer_detail.status_code == 403
        assert customer_list.json()["error"]["code"] == "FORBIDDEN"
        assert customer_detail.json()["error"]["code"] == "FORBIDDEN"

    anyio.run(run)
