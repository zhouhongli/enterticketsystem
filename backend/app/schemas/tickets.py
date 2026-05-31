from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import TicketStatus


class CustomerTicketCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=4000)

    @field_validator("category_id", "title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class CustomerTicketMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class InternalTicketAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assignee_user_id: str = Field(min_length=1)

    @field_validator("assignee_user_id", mode="before")
    @classmethod
    def strip_assignee_user_id(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class InternalTicketMessageCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=2000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class InternalTicketStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TicketStatus


def customer_ticket_detail_response(ticket: dict[str, Any]) -> dict[str, Any]:
    return customer_ticket_detail_with_messages_response(ticket, [])


def customer_ticket_list_item_response(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ticket["id"],
        "title": ticket["title"],
        "category_name": ticket["category_name_snapshot"],
        "status": ticket["status"],
        "created_at": ticket["created_at"],
    }


def message_response(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message["id"],
        "sender_role": message["sender_role_snapshot"],
        "sender_name": message["sender_name_snapshot"],
        "content": message["content"],
        "sent_at": message["sent_at"],
    }


def customer_ticket_detail_with_messages_response(
    ticket: dict[str, Any], messages: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": ticket["id"],
        "title": ticket["title"],
        "description": ticket["description"],
        "category_name": ticket["category_name_snapshot"],
        "status": ticket["status"],
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
        "messages": [message_response(message) for message in messages],
    }


def user_brief_response(user: dict[str, Any] | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user["id"],
        "username": user["username"],
    }


def internal_ticket_list_item_response(bundle: dict[str, Any]) -> dict[str, Any]:
    ticket = bundle["ticket"]
    return {
        "id": ticket["id"],
        "title": ticket["title"],
        "customer": user_brief_response(bundle["customer"]),
        "category_name": ticket["category_name_snapshot"],
        "status": ticket["status"],
        "assignee": user_brief_response(bundle["assignee"]),
        "created_at": ticket["created_at"],
    }


def audit_log_response(bundle: dict[str, Any]) -> dict[str, Any]:
    audit_log = bundle["audit_log"]
    actor = bundle["actor"]
    return {
        "id": audit_log["id"],
        "action": audit_log["action"],
        "actor": {
            "id": audit_log["actor_user_id"],
            "role": audit_log["actor_role_snapshot"],
            "username": actor["username"] if actor is not None else "",
        },
        "changes": audit_log["changes"],
        "occurred_at": audit_log["occurred_at"],
    }


def internal_ticket_detail_response(bundle: dict[str, Any]) -> dict[str, Any]:
    ticket = bundle["ticket"]
    return {
        "id": ticket["id"],
        "title": ticket["title"],
        "description": ticket["description"],
        "category_name": ticket["category_name_snapshot"],
        "customer": user_brief_response(bundle["customer"]),
        "status": ticket["status"],
        "assignee": user_brief_response(bundle["assignee"]),
        "created_at": ticket["created_at"],
        "updated_at": ticket["updated_at"],
        "messages": [message_response(message) for message in bundle["messages"]],
        "audit_logs": [
            audit_log_response(audit_log_bundle)
            for audit_log_bundle in bundle["audit_logs"]
        ],
    }


def internal_ticket_assignment_response(bundle: dict[str, Any]) -> dict[str, Any]:
    ticket = bundle["ticket"]
    return {
        "ticket_id": ticket["id"],
        "assignee": user_brief_response(bundle["assignee"]),
        "status": ticket["status"],
        "updated_at": ticket["updated_at"],
    }


def internal_ticket_status_response(ticket: dict[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": ticket["id"],
        "status": ticket["status"],
        "updated_at": ticket["updated_at"],
    }
