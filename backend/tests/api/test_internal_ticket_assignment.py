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


def assert_assignment_payload_has_no_sensitive_fields(payload: dict) -> None:
    assert set(payload.keys()) == {"ticket_id", "assignee", "status", "updated_at"}
    serialized = str(payload)
    assert "assignee_user_id" not in serialized
    assert "customer_user_id" not in serialized
    assert "email" not in serialized
    assert "password_hash" not in serialized
    assert "token_hash" not in serialized
    assert "audit_logs" not in serialized


def test_admin_assigns_unassigned_ticket_to_active_agent_without_status_change(
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
        ticket_id="ticket-assign",
        title="待分配工单",
        description="需要安排客服处理。",
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
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": f"  {agent['id']}  "},
            )

        stored_ticket = repo.store.read()["tickets"][0]
        logs = ticket_audit_logs(repo, ticket["id"])
        payload = response.json()

        assert response.status_code == 200
        assert payload == {
            "ticket_id": ticket["id"],
            "assignee": {"id": agent["id"], "username": "agent01"},
            "status": "unassigned",
            "updated_at": stored_ticket["updated_at"],
        }
        assert_assignment_payload_has_no_sensitive_fields(payload)
        assert stored_ticket["assignee_user_id"] == agent["id"]
        assert stored_ticket["status"] == "unassigned"
        assert stored_ticket["updated_at"] != "2026-05-26T10:20:30Z"
        assert logs == [
            {
                "id": logs[0]["id"],
                "action": "ticket_assigned",
                "actor_user_id": admin["id"],
                "actor_role_snapshot": "admin",
                "target_type": "ticket",
                "target_id": ticket["id"],
                "ticket_id": ticket["id"],
                "changes": {
                    "assignee_user_id": {"before": None, "after": agent["id"]}
                },
                "occurred_at": logs[0]["occurred_at"],
            }
        ]
        assert stored_ticket["updated_at"] == logs[0]["occurred_at"]

    anyio.run(run)


def test_admin_reassigns_ticket_and_detail_exposes_assignment_audit_log(
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
    old_agent, _ = add_user_with_session(
        repo,
        username="agent01",
        email="agent01@example.com",
        role=UserRole.AGENT,
    )
    new_agent, _ = add_user_with_session(
        repo,
        username="agent02",
        email="agent02@example.com",
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
        ticket_id="ticket-reassign",
        title="处理中工单",
        description="需要改派。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:40:30Z",
        status=TicketStatus.PROCESSING,
        assignee_user_id=old_agent["id"],
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": new_agent["id"]},
            )
            detail_response = await client.get(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}"
            )

        stored_ticket = repo.store.read()["tickets"][0]
        logs = ticket_audit_logs(repo, ticket["id"])
        detail_payload = detail_response.json()

        assert response.status_code == 200
        assert response.json()["assignee"] == {
            "id": new_agent["id"],
            "username": "agent02",
        }
        assert response.json()["status"] == "processing"
        assert stored_ticket["assignee_user_id"] == new_agent["id"]
        assert stored_ticket["status"] == "processing"
        assert logs == [
            {
                "id": logs[0]["id"],
                "action": "ticket_reassigned",
                "actor_user_id": admin["id"],
                "actor_role_snapshot": "admin",
                "target_type": "ticket",
                "target_id": ticket["id"],
                "ticket_id": ticket["id"],
                "changes": {
                    "assignee_user_id": {
                        "before": old_agent["id"],
                        "after": new_agent["id"],
                    }
                },
                "occurred_at": logs[0]["occurred_at"],
            }
        ]
        assert detail_response.status_code == 200
        assert detail_payload["assignee"] == {
            "id": new_agent["id"],
            "username": "agent02",
        }
        assert detail_payload["audit_logs"][0]["action"] == "ticket_reassigned"
        assert detail_payload["audit_logs"][0]["changes"] == logs[0]["changes"]

    anyio.run(run)


def test_non_admin_roles_cannot_assign_ticket(tmp_path) -> None:
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
    customer, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-non-admin",
        title="权限边界工单",
        description="只有管理员能分配。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            anonymous = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"]},
            )
            client.cookies.set(settings.session_cookie_name, agent_token)
            agent_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"]},
            )
            client.cookies.set(settings.session_cookie_name, customer_token)
            customer_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"]},
            )

        assert anonymous.status_code == 401
        assert anonymous.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
        assert agent_response.status_code == 403
        assert customer_response.status_code == 403
        assert agent_response.json()["error"]["code"] == "FORBIDDEN"
        assert customer_response.json()["error"]["code"] == "FORBIDDEN"
        stored_ticket = repo.store.read()["tickets"][0]
        assert stored_ticket["assignee_user_id"] is None
        assert ticket_audit_logs(repo, ticket["id"]) == []

    anyio.run(run)


def test_invalid_assignee_or_missing_ticket_does_not_change_assignment(
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
    other_admin, _ = add_user_with_session(
        repo,
        username="admin02",
        email="admin02@example.com",
        role=UserRole.ADMIN,
    )
    disabled_agent, _ = add_user_with_session(
        repo,
        username="agent-disabled",
        email="agent-disabled@example.com",
        role=UserRole.AGENT,
        status=UserStatus.DISABLED,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-invalid-assignee",
        title="负责人校验工单",
        description="只能分配给有效客服。",
        category=category,
        customer_user=customer,
        created_at="2026-05-26T10:20:30Z",
        updated_at="2026-05-26T10:20:30Z",
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            client.cookies.set(settings.session_cookie_name, admin_token)
            customer_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": customer["id"]},
            )
            admin_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": other_admin["id"]},
            )
            disabled_agent_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": disabled_agent["id"]},
            )
            missing_agent_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": "missing-agent"},
            )
            missing_ticket_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/missing-ticket/assignment",
                json={"assignee_user_id": disabled_agent["id"]},
            )

        responses = [
            customer_response,
            admin_response,
            disabled_agent_response,
            missing_agent_response,
        ]
        assert [response.status_code for response in responses] == [409] * 4
        assert [
            response.json()["error"]["code"] for response in responses
        ] == ["CONFLICT"] * 4
        assert missing_ticket_response.status_code == 404
        assert missing_ticket_response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
        stored_ticket = repo.store.read()["tickets"][0]
        assert stored_ticket["assignee_user_id"] is None
        assert stored_ticket["updated_at"] == "2026-05-26T10:20:30Z"
        assert ticket_audit_logs(repo, ticket["id"]) == []

    anyio.run(run)


def test_closed_ticket_and_invalid_request_body_are_rejected_without_changes(
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
        ticket_id="ticket-closed",
        title="已关闭工单",
        description="关闭后不能重新分配。",
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
            closed_response = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"]},
            )
            missing_field = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={},
            )
            empty_field = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": "  "},
            )
            spoofed_field = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/assignment",
                json={"assignee_user_id": agent["id"], "status": "processing"},
            )

        assert closed_response.status_code == 409
        assert closed_response.json()["error"]["code"] == "CONFLICT"
        validation_responses = [missing_field, empty_field, spoofed_field]
        assert [response.status_code for response in validation_responses] == [422] * 3
        assert [
            response.json()["error"]["code"] for response in validation_responses
        ] == ["VALIDATION_ERROR"] * 3
        stored_ticket = repo.store.read()["tickets"][0]
        assert stored_ticket["status"] == "closed"
        assert stored_ticket["assignee_user_id"] is None
        assert stored_ticket["updated_at"] == "2026-05-26T11:20:30Z"
        assert ticket_audit_logs(repo, ticket["id"]) == []

    anyio.run(run)
