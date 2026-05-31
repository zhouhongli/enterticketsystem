from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.domain.enums import (
    AuditAction,
    CategoryStatus,
    TicketStatus,
    UserRole,
    UserStatus,
)


def new_id() -> str:
    return str(uuid4())


def utc_now(offset: timedelta | None = None) -> str:
    value = datetime.now(timezone.utc)
    if offset is not None:
        value += offset
    return format_utc(value)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def format_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def user_record(
    *,
    username: str,
    email: str,
    password_hash: str,
    role: UserRole,
    status: UserStatus = UserStatus.ACTIVE,
    user_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    return {
        "id": user_id or new_id(),
        "username": username.strip(),
        "email": email.strip().lower(),
        "password_hash": password_hash,
        "role": role.value,
        "status": status.value,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def category_record(
    *,
    name: str,
    created_by_user_id: str,
    status: CategoryStatus = CategoryStatus.ACTIVE,
    category_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    return {
        "id": category_id or new_id(),
        "name": name.strip(),
        "status": status.value,
        "created_by_user_id": created_by_user_id,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def ticket_record(
    *,
    title: str,
    description: str,
    category: dict[str, Any],
    customer_user_id: str,
    ticket_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    return {
        "id": ticket_id or new_id(),
        "title": title.strip(),
        "description": description.strip(),
        "category_id": category["id"],
        "category_name_snapshot": category["name"],
        "customer_user_id": customer_user_id,
        "status": TicketStatus.UNASSIGNED.value,
        "assignee_user_id": None,
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def message_record(
    *,
    ticket_id: str,
    sender_user: dict[str, Any],
    content: str,
    message_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    return {
        "id": message_id or new_id(),
        "ticket_id": ticket_id,
        "sender_user_id": sender_user["id"],
        "sender_role_snapshot": sender_user["role"],
        "sender_name_snapshot": sender_user["username"],
        "content": content.strip(),
        "sent_at": now or utc_now(),
    }


def audit_log_record(
    *,
    action: AuditAction,
    actor_user: dict[str, Any],
    target_type: str,
    target_id: str,
    changes: dict[str, Any],
    ticket_id: str | None = None,
    audit_log_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    return {
        "id": audit_log_id or new_id(),
        "action": action.value,
        "actor_user_id": actor_user["id"],
        "actor_role_snapshot": actor_user["role"],
        "target_type": target_type,
        "target_id": target_id,
        "ticket_id": ticket_id,
        "changes": changes,
        "occurred_at": now or utc_now(),
    }


def session_record(
    *,
    token_hash: str,
    user_id: str,
    expires_at: str,
    session_id: str | None = None,
    now: str | None = None,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    return {
        "id": session_id or new_id(),
        "token_hash": token_hash,
        "user_id": user_id,
        "created_at": timestamp,
        "last_seen_at": timestamp,
        "expires_at": expires_at,
        "revoked_at": None,
    }
