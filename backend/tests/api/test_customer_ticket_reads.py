from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import customer
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


def assert_customer_payload_has_no_internal_fields(payload: dict) -> None:
    serialized = str(payload)
    assert "assignee_user_id" not in serialized
    assert "assignee" not in serialized
    assert "customer_user_id" not in serialized
    assert "customer01@example.com" not in serialized
    assert "customer02@example.com" not in serialized
    assert "agent01@example.com" not in serialized
    assert "audit_logs" not in serialized
    assert "internal note" not in serialized
    assert "actor_user_id" not in serialized


def test_customer_lists_only_own_tickets_in_created_at_desc_order(tmp_path) -> None:
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
    other_customer, _ = add_user_with_session(
        repo,
        username="customer02",
        email="customer02@example.com",
        role=UserRole.CUSTOMER,
    )
    agent, _ = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    older = add_ticket(
        repo,
        ticket_id="ticket-own-older",
        title="较早工单",
        description="较早的客户问题。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
    )
    newer = add_ticket(
        repo,
        ticket_id="ticket-own-newer",
        title="较新工单",
        description="较新的客户问题。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-27T10:20:30Z",
        assignee_user_id=agent["id"],
    )
    add_ticket(
        repo,
        ticket_id="ticket-other",
        title="他人工单",
        description="不应出现在列表中。",
        category=category,
        customer_user=other_customer,
        created_at="2026-05-28T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.get(f"{API_PREFIX}/customer/tickets")

        payload = response.json()

        assert response.status_code == 200
        assert payload == {
            "items": [
                {
                    "id": newer["id"],
                    "title": "较新工单",
                    "category_name": "产品故障",
                    "status": "unassigned",
                    "created_at": "2026-05-27T10:20:30Z",
                },
                {
                    "id": older["id"],
                    "title": "较早工单",
                    "category_name": "产品故障",
                    "status": "unassigned",
                    "created_at": "2026-05-26T10:20:30Z",
                },
            ]
        }
        assert [set(item.keys()) for item in payload["items"]] == [
            {"id", "title", "category_name", "status", "created_at"},
            {"id", "title", "category_name", "status", "created_at"},
        ]
        assert "ticket-other" not in str(payload)
        assert_customer_payload_has_no_internal_fields(payload)

    anyio.run(run)


def test_customer_detail_returns_snapshot_times_and_public_messages_only(
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
    customer_user, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    agent, _ = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-detail",
        title="无法正常使用服务",
        description="登录后页面无法继续操作。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:24:00Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=agent["id"],
    )
    repo.update_category_name(
        category_id=category["id"],
        name="产品使用问题",
        actor_user=admin,
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
        sender_user=customer_user,
        content="请协助处理。",
        sent_at="2026-05-26T10:22:00Z",
    )

    def add_internal_record(data: dict) -> None:
        data["audit_logs"].append(
            {
                "id": "audit-internal",
                "action": "ticket_assigned",
                "actor_user_id": admin["id"],
                "actor_role_snapshot": "admin",
                "target_type": "ticket",
                "target_id": ticket["id"],
                "ticket_id": ticket["id"],
                "changes": {
                    "assignee_user_id": {
                        "before": None,
                        "after": agent["id"],
                    },
                    "note": "internal note",
                },
                "occurred_at": "2026-05-26T10:21:00Z",
            }
        )

    repo.store.transaction(add_internal_record)
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, customer_token)
            response = await client.get(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}"
            )

        payload = response.json()

        assert response.status_code == 200
        assert payload == {
            "id": ticket["id"],
            "title": "无法正常使用服务",
            "description": "登录后页面无法继续操作。",
            "category_name": "产品故障",
            "status": "processing",
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
        }
        assert_customer_payload_has_no_internal_fields(payload)
        assert repo.get_category(category["id"])["name"] == "产品使用问题"

    anyio.run(run)


def test_other_customer_and_missing_ticket_return_404_without_resource_content(
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
        description="其他客户不能读取。",
        category=category,
        customer_user=owner,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, other_token)
            other_customer_response = await client.get(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}"
            )
            missing_response = await client.get(
                f"{API_PREFIX}/customer/tickets/missing-ticket"
            )

        responses = [other_customer_response, missing_response]
        assert [response.status_code for response in responses] == [404, 404]
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["RESOURCE_NOT_FOUND", "RESOURCE_NOT_FOUND"]
        for response in responses:
            payload_text = str(response.json())
            assert ticket["id"] not in payload_text
            assert "归属客户一的工单" not in payload_text
            assert "其他客户不能读取" not in payload_text

    anyio.run(run)


def test_login_required_and_non_customer_roles_cannot_read_customer_tickets(
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
        description="仅客户本人可读。",
        category=category,
        customer_user=customer_user,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous_list = await client.get(f"{API_PREFIX}/customer/tickets")
            anonymous_detail = await client.get(
                f"{API_PREFIX}/customer/tickets/{ticket['id']}"
            )

            role_responses = []
            for token in (agent_token, admin_token):
                client.cookies.set(settings.session_cookie_name, token)
                role_responses.append(
                    await client.get(f"{API_PREFIX}/customer/tickets")
                )
                role_responses.append(
                    await client.get(
                        f"{API_PREFIX}/customer/tickets/{ticket['id']}"
                    )
                )

        assert anonymous_list.status_code == 401
        assert anonymous_detail.status_code == 401
        assert anonymous_list.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert anonymous_detail.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert [response.status_code for response in role_responses] == [403] * 4
        assert [
            response.json()["error"]["code"] for response in role_responses
        ] == ["FORBIDDEN"] * 4

    anyio.run(run)
