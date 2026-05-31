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


def ticket_audit_logs(repo: JsonRepository, ticket_id: str) -> list[dict]:
    return [
        record
        for record in repo.store.read()["audit_logs"]
        if record["ticket_id"] == ticket_id
    ]


def assert_status_payload_has_no_sensitive_fields(payload: dict) -> None:
    assert set(payload.keys()) == {"ticket_id", "status", "updated_at"}
    serialized = str(payload)
    assert "assignee_user_id" not in serialized
    assert "customer_user_id" not in serialized
    assert "email" not in serialized
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert "audit_logs" not in serialized


def test_admin_can_advance_unassigned_ticket_without_assignee(tmp_path) -> None:
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
        ticket_id="ticket-admin-status",
        title="待分配工单",
        description="管理员可直接推进。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
        status=TicketStatus.UNASSIGNED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        logs = ticket_audit_logs(repo, ticket["id"])
        payload = response.json()

        assert response.status_code == 200
        assert payload == {
            "ticket_id": ticket["id"],
            "status": "processing",
            "updated_at": stored_ticket["updated_at"],
        }
        assert_status_payload_has_no_sensitive_fields(payload)
        assert stored_ticket["status"] == "processing"
        assert stored_ticket["assignee_user_id"] is None
        assert stored_ticket["updated_at"] != "2026-05-26T10:20:30Z"
        assert logs == [
            {
                "id": logs[0]["id"],
                "action": "ticket_status_changed",
                "actor_user_id": admin["id"],
                "actor_role_snapshot": "admin",
                "target_type": "ticket",
                "target_id": ticket["id"],
                "ticket_id": ticket["id"],
                "changes": {
                    "status": {"before": "unassigned", "after": "processing"}
                },
                "occurred_at": logs[0]["occurred_at"],
            }
        ]
        assert stored_ticket["updated_at"] == logs[0]["occurred_at"]

    anyio.run(run)


def test_responsible_agent_advances_ticket_through_linear_flow_to_closed(
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
        ticket_id="ticket-agent-linear-status",
        title="已分配工单",
        description="负责客服线性推进。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        status=TicketStatus.UNASSIGNED,
        assignee_user_id=agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, agent_token)
            processing = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing"},
            )
            resolved = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "resolved"},
            )
            closed = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "closed"},
            )

        assert [response.status_code for response in [processing, resolved, closed]] == [
            200,
            200,
            200,
        ]
        assert [response.json()["status"] for response in [processing, resolved, closed]] == [
            "processing",
            "resolved",
            "closed",
        ]
        stored_ticket = repo.store.read()["tickets"][0]
        logs = ticket_audit_logs(repo, ticket["id"])
        assert stored_ticket["status"] == "closed"
        assert stored_ticket["assignee_user_id"] == agent["id"]
        assert [record["action"] for record in logs] == [
            "ticket_status_changed",
            "ticket_status_changed",
            "ticket_status_changed",
        ]
        assert [record["changes"]["status"] for record in logs] == [
            {"before": "unassigned", "after": "processing"},
            {"before": "processing", "after": "resolved"},
            {"before": "resolved", "after": "closed"},
        ]

    anyio.run(run)


def test_non_responsible_agent_customer_and_anonymous_cannot_advance_status(
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
    _, other_agent_token = add_user_with_session(
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
        ticket_id="ticket-status-permission",
        title="权限边界工单",
        description="非负责人不能推进。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
        assignee_user_id=responsible_agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing"},
            )
            client.cookies.set(settings.session_cookie_name, other_agent_token)
            other_agent = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing"},
            )
            client.cookies.set(settings.session_cookie_name, customer_token)
            customer_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing"},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert other_agent.status_code == 403
        assert other_agent.json()["error"]["code"] == "FORBIDDEN"
        assert customer_response.status_code == 403
        assert customer_response.json()["error"]["code"] == "FORBIDDEN"
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["updated_at"] == "2026-05-26T10:20:30Z"
        assert ticket_audit_logs(repo, ticket["id"]) == []

    anyio.run(run)


def test_missing_closed_and_invalid_transitions_do_not_change_status(tmp_path) -> None:
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
    open_ticket = add_ticket(
        repo,
        ticket_id="ticket-invalid-transition",
        title="处理中工单",
        description="不能跳级或回退。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:30:30Z",
        status=TicketStatus.PROCESSING,
    )
    closed_ticket = add_ticket(
        repo,
        ticket_id="ticket-closed-status",
        title="已关闭工单",
        description="关闭后不能推进。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T11:20:30Z",
        updated_at="2026-05-26T11:30:30Z",
        status=TicketStatus.CLOSED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            missing = await client.patch(
                f"{API_PREFIX}/internal/tickets/missing-ticket/status",
                json={"status": "processing"},
            )
            skip = await client.patch(
                f"{API_PREFIX}/internal/tickets/{open_ticket['id']}/status",
                json={"status": "closed"},
            )
            back = await client.patch(
                f"{API_PREFIX}/internal/tickets/{open_ticket['id']}/status",
                json={"status": "unassigned"},
            )
            same = await client.patch(
                f"{API_PREFIX}/internal/tickets/{open_ticket['id']}/status",
                json={"status": "processing"},
            )
            closed = await client.patch(
                f"{API_PREFIX}/internal/tickets/{closed_ticket['id']}/status",
                json={"status": "closed"},
            )

        stored_tickets = {ticket["id"]: ticket for ticket in repo.store.read()["tickets"]}
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        conflict_responses = [skip, back, same, closed]
        assert [response.status_code for response in conflict_responses] == [409] * 4
        assert [
            response.json()["error"]["code"] for response in conflict_responses
        ] == ["CONFLICT"] * 4
        assert stored_tickets[open_ticket["id"]]["status"] == "processing"
        assert stored_tickets[open_ticket["id"]]["updated_at"] == "2026-05-26T10:30:30Z"
        assert stored_tickets[closed_ticket["id"]]["status"] == "closed"
        assert stored_tickets[closed_ticket["id"]]["updated_at"] == "2026-05-26T11:30:30Z"
        assert ticket_audit_logs(repo, open_ticket["id"]) == []
        assert ticket_audit_logs(repo, closed_ticket["id"]) == []

    anyio.run(run)


def test_invalid_status_request_body_is_rejected_without_changes(tmp_path) -> None:
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
        ticket_id="ticket-status-validation",
        title="状态校验工单",
        description="非法请求不能推进。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            missing_status = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={},
            )
            invalid_status = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "invalid"},
            )
            spoofed_fields = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "processing", "assignee_user_id": "agent01"},
            )

        responses = [missing_status, invalid_status, spoofed_fields]
        stored_ticket = repo.store.read()["tickets"][0]
        assert [response.status_code for response in responses] == [422] * 3
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["VALIDATION_ERROR"] * 3
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["updated_at"] == "2026-05-26T10:20:30Z"
        assert ticket_audit_logs(repo, ticket["id"]) == []

    anyio.run(run)


def test_closing_ticket_blocks_assignment_and_internal_messages(tmp_path) -> None:
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
        ticket_id="ticket-close-writes",
        title="待关闭工单",
        description="关闭后禁止写操作。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:40:30Z",
        status=TicketStatus.RESOLVED,
        assignee_user_id=agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            close_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "closed"},
            )
            assignment_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"]},
            )
            message_response = await client.post(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/messages",
                json={"content": "关闭后留言。"},
            )
            status_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "closed"},
            )

        assert close_response.status_code == 200
        post_close_responses = [assignment_response, message_response, status_response]
        assert [response.status_code for response in post_close_responses] == [409] * 3
        assert [
            response.json()["error"]["code"] for response in post_close_responses
        ] == ["CONFLICT"] * 3
        stored_ticket = repo.store.read()["tickets"][0]
        assert stored_ticket["status"] == "closed"
        assert stored_ticket["assignee_user_id"] == agent["id"]
        assert repo.store.read()["messages"] == []
        assert [record["action"] for record in ticket_audit_logs(repo, ticket["id"])] == [
            "ticket_status_changed"
        ]

    anyio.run(run)
