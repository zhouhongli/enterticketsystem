from __future__ import annotations

import anyio
import httpx
from fastapi import FastAPI

from app.api.errors import install_exception_handlers
from app.api.routes import auth, customer, internal
from app.config import Settings, get_settings
from app.domain.enums import TicketStatus, UserRole
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
    app.include_router(customer.router, prefix=API_PREFIX)
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
    password: str,
    role: UserRole,
) -> tuple[dict, str]:
    user = repo.add_user(
        username=username,
        email=email,
        password_hash=PasswordService().hash_password(password),
        role=role,
    )
    token = SessionService(repo, ttl_hours=8).create_session(user["id"]).raw_token
    return user, token


def add_ticket(
    repo: JsonRepository,
    *,
    ticket_id: str,
    category: dict,
    customer_user: dict,
    status: TicketStatus = TicketStatus.UNASSIGNED,
) -> dict:
    record = {
        "id": ticket_id,
        "title": "错误响应测试工单",
        "description": "用于验证统一错误结构。",
        "category_id": category["id"],
        "category_name_snapshot": category["name"],
        "customer_user_id": customer_user["id"],
        "status": status.value,
        "assignee_user_id": None,
        "created_at": "2026-05-26T10:20:30Z",
        "updated_at": "2026-05-26T10:20:30Z",
    }

    def save(data: dict) -> dict:
        data["tickets"].append(record)
        return record

    return repo.store.transaction(save)


async def make_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


def assert_error_contract(
    response: httpx.Response,
    *,
    status_code: int,
    code: str,
    has_field_errors: bool = False,
) -> None:
    payload = response.json()
    assert response.status_code == status_code
    assert set(payload.keys()) == {"error"}
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    assert payload["error"]["message"]
    if has_field_errors:
        assert isinstance(payload["error"]["field_errors"], dict)
        assert payload["error"]["field_errors"]
    else:
        assert "field_errors" not in payload["error"]


def test_common_error_responses_use_unified_contract(tmp_path) -> None:
    settings = make_settings(tmp_path)
    repo = make_repo(settings)
    admin, admin_token = add_user_with_session(
        repo,
        username="admin01",
        email="admin01@example.com",
        password="AdminPassword123",
        role=UserRole.ADMIN,
    )
    customer, customer_token = add_user_with_session(
        repo,
        username="customer01",
        email="customer01@example.com",
        password="CustomerPassword123",
        role=UserRole.CUSTOMER,
    )
    category = repo.create_category(name="产品故障", actor_user=admin)
    ticket = add_ticket(
        repo,
        ticket_id="ticket-closed",
        category=category,
        customer_user=customer,
        status=TicketStatus.CLOSED,
    )
    app = make_app(settings)

    async def run() -> None:
        async with await make_client(app) as client:
            validation = await client.post(
                f"{API_PREFIX}/auth/register",
                json={"username": "bad"},
            )
            login_failed = await client.post(
                f"{API_PREFIX}/auth/login",
                json={"identifier": "missing", "password": "bad-password"},
            )
            anonymous = await client.get(f"{API_PREFIX}/internal/tickets")
            client.cookies.set(settings.session_cookie_name, customer_token)
            forbidden = await client.get(f"{API_PREFIX}/internal/tickets")
            not_found = await client.get(
                f"{API_PREFIX}/customer/tickets/missing-ticket"
            )
            client.cookies.set(settings.session_cookie_name, admin_token)
            conflict = await client.patch(
                f"{API_PREFIX}/internal/tickets/{ticket['id']}/status",
                json={"status": "closed"},
            )

        assert_error_contract(
            validation,
            status_code=422,
            code="VALIDATION_ERROR",
            has_field_errors=True,
        )
        assert_error_contract(login_failed, status_code=401, code="LOGIN_FAILED")
        assert_error_contract(
            anonymous,
            status_code=401,
            code="AUTHENTICATION_REQUIRED",
        )
        assert_error_contract(forbidden, status_code=403, code="FORBIDDEN")
        assert_error_contract(not_found, status_code=404, code="RESOURCE_NOT_FOUND")
        assert_error_contract(conflict, status_code=409, code="CONFLICT")

    anyio.run(run)
