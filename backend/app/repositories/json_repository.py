from __future__ import annotations

from typing import Any

from app.domain.enums import (
    AuditAction,
    CategoryStatus,
    TicketStatus,
    UserRole,
    UserStatus,
)
from app.domain.models import (
    audit_log_record,
    category_record,
    message_record,
    session_record,
    ticket_record,
    user_record,
    utc_now,
)
from app.storage.json_store import JsonFileStore


class JsonRepository:
    def __init__(self, store: JsonFileStore):
        self.store = store

    def list_users(self) -> list[dict[str, Any]]:
        return self.store.read()["users"]

    def list_users_by_role(self, role: UserRole) -> list[dict[str, Any]]:
        return sorted(
            [user for user in self.list_users() if user["role"] == role.value],
            key=lambda user: user["created_at"],
            reverse=True,
        )

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        return self._find_one("users", lambda user: user["id"] == user_id)

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized = username.strip()
        return self._find_one("users", lambda user: user["username"] == normalized)

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        normalized = email.strip().lower()
        return self._find_one("users", lambda user: user["email"] == normalized)

    def add_user(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        role: UserRole,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> dict[str, Any]:
        record = user_record(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            status=status,
        )

        def save(data: dict[str, Any]) -> dict[str, Any]:
            self._assert_unique_user_identifiers(
                data, record["username"], record["email"]
            )
            data["users"].append(record)
            return record

        return self.store.transaction(save)

    def update_user_status(
        self, user_id: str, status: UserStatus
    ) -> dict[str, Any] | None:
        timestamp = utc_now()

        def update(data: dict[str, Any]) -> dict[str, Any] | None:
            for user in data["users"]:
                if user["id"] == user_id:
                    user["status"] = status.value
                    user["updated_at"] = timestamp
                    return user
            return None

        return self.store.transaction(update)

    def update_customer_status(
        self,
        *,
        user_id: str,
        status: UserStatus,
        actor_user: dict[str, Any],
    ) -> dict[str, Any] | None:
        timestamp = utc_now()

        def update(data: dict[str, Any]) -> dict[str, Any] | None:
            user = self._find_one_in_data(
                data, "users", lambda item: item["id"] == user_id
            )
            if user is None:
                return None
            if user["role"] != UserRole.CUSTOMER.value:
                raise ValueError("Target user is not customer")

            before = user["status"]
            user["status"] = status.value
            user["updated_at"] = timestamp

            if status == UserStatus.DISABLED:
                for session in data["sessions"]:
                    if session["user_id"] == user_id and session["revoked_at"] is None:
                        session["revoked_at"] = timestamp

            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.CUSTOMER_STATUS_CHANGED,
                    actor_user=actor_user,
                    target_type="user",
                    target_id=user_id,
                    changes={"status": {"before": before, "after": status.value}},
                    now=timestamp,
                )
            )
            return user

        return self.store.transaction(update)

    def has_admin(self) -> bool:
        return any(user["role"] == UserRole.ADMIN.value for user in self.list_users())

    def list_categories(self) -> list[dict[str, Any]]:
        return sorted(
            self.store.read()["categories"],
            key=lambda category: category["created_at"],
            reverse=True,
        )

    def list_audit_logs(self) -> list[dict[str, Any]]:
        return sorted(
            self.store.read()["audit_logs"],
            key=lambda log: log["occurred_at"],
            reverse=True,
        )

    def list_active_categories(self) -> list[dict[str, Any]]:
        return [
            category
            for category in self.list_categories()
            if category["status"] == CategoryStatus.ACTIVE.value
        ]

    def get_category(self, category_id: str) -> dict[str, Any] | None:
        return self._find_one(
            "categories", lambda category: category["id"] == category_id
        )

    def create_category(
        self, *, name: str, actor_user: dict[str, Any]
    ) -> dict[str, Any]:
        timestamp = utc_now()
        record = category_record(
            name=name, created_by_user_id=actor_user["id"], now=timestamp
        )

        def save(data: dict[str, Any]) -> dict[str, Any]:
            self._assert_unique_category_name(data, record["name"])
            data["categories"].append(record)
            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.CATEGORY_CREATED,
                    actor_user=actor_user,
                    target_type="category",
                    target_id=record["id"],
                    changes={
                        "name": {"before": None, "after": record["name"]},
                        "status": {"before": None, "after": record["status"]},
                    },
                    now=timestamp,
                )
            )
            return record

        return self.store.transaction(save)

    def update_category_name(
        self, *, category_id: str, name: str, actor_user: dict[str, Any]
    ) -> dict[str, Any] | None:
        normalized_name = name.strip()
        timestamp = utc_now()

        def update(data: dict[str, Any]) -> dict[str, Any] | None:
            category = self._find_one_in_data(
                data, "categories", lambda item: item["id"] == category_id
            )
            if category is None:
                return None
            if category["name"] != normalized_name:
                self._assert_unique_category_name(data, normalized_name)
            before = category["name"]
            category["name"] = normalized_name
            category["updated_at"] = timestamp
            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.CATEGORY_UPDATED,
                    actor_user=actor_user,
                    target_type="category",
                    target_id=category_id,
                    changes={"name": {"before": before, "after": normalized_name}},
                    now=timestamp,
                )
            )
            return category

        return self.store.transaction(update)

    def update_category_status(
        self,
        *,
        category_id: str,
        status: CategoryStatus,
        actor_user: dict[str, Any],
    ) -> dict[str, Any] | None:
        timestamp = utc_now()

        def update(data: dict[str, Any]) -> dict[str, Any] | None:
            category = self._find_one_in_data(
                data, "categories", lambda item: item["id"] == category_id
            )
            if category is None:
                return None
            before = category["status"]
            category["status"] = status.value
            category["updated_at"] = timestamp
            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.CATEGORY_STATUS_CHANGED,
                    actor_user=actor_user,
                    target_type="category",
                    target_id=category_id,
                    changes={"status": {"before": before, "after": status.value}},
                    now=timestamp,
                )
            )
            return category

        return self.store.transaction(update)

    def create_customer_ticket(
        self,
        *,
        category_id: str,
        title: str,
        description: str,
        customer_user: dict[str, Any],
    ) -> dict[str, Any] | None:
        timestamp = utc_now()

        def save(data: dict[str, Any]) -> dict[str, Any] | None:
            category = self._find_one_in_data(
                data,
                "categories",
                lambda item: item["id"] == category_id
                and item["status"] == CategoryStatus.ACTIVE.value,
            )
            if category is None:
                return None

            record = ticket_record(
                title=title,
                description=description,
                category=category,
                customer_user_id=customer_user["id"],
                now=timestamp,
            )
            data["tickets"].append(record)
            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.TICKET_CREATED,
                    actor_user=customer_user,
                    target_type="ticket",
                    target_id=record["id"],
                    ticket_id=record["id"],
                    changes={
                        "status": {
                            "before": None,
                            "after": record["status"],
                        }
                    },
                    now=timestamp,
                )
            )
            return record

        return self.store.transaction(save)

    def list_customer_tickets(self, customer_user_id: str) -> list[dict[str, Any]]:
        return sorted(
            [
                ticket
                for ticket in self.store.read()["tickets"]
                if ticket["customer_user_id"] == customer_user_id
            ],
            key=lambda ticket: ticket["created_at"],
            reverse=True,
        )

    def get_customer_ticket_with_messages(
        self, *, ticket_id: str, customer_user_id: str
    ) -> dict[str, Any] | None:
        data = self.store.read()
        ticket = self._find_one_in_data(
            data,
            "tickets",
            lambda item: item["id"] == ticket_id
            and item["customer_user_id"] == customer_user_id,
        )
        if ticket is None:
            return None
        return {
            "ticket": ticket,
            "messages": sorted(
                [
                    message
                    for message in data["messages"]
                    if message["ticket_id"] == ticket_id
                ],
                key=lambda message: message["sent_at"],
            ),
        }

    def add_customer_ticket_message(
        self,
        *,
        ticket_id: str,
        customer_user: dict[str, Any],
        content: str,
    ) -> dict[str, Any] | str:
        timestamp = utc_now()

        def save(data: dict[str, Any]) -> dict[str, Any] | str:
            ticket = self._find_one_in_data(
                data,
                "tickets",
                lambda item: item["id"] == ticket_id
                and item["customer_user_id"] == customer_user["id"],
            )
            if ticket is None:
                return "not_found"
            if ticket["status"] == "closed":
                return "closed"

            record = message_record(
                ticket_id=ticket_id,
                sender_user=customer_user,
                content=content,
                now=timestamp,
            )
            data["messages"].append(record)
            ticket["updated_at"] = timestamp
            return record

        return self.store.transaction(save)

    def list_internal_tickets(
        self, ticket_status: str | None = None
    ) -> list[dict[str, Any]]:
        data = self.store.read()
        tickets = [
            ticket
            for ticket in data["tickets"]
            if ticket_status is None or ticket["status"] == ticket_status
        ]
        return [
            self._internal_ticket_bundle(data, ticket)
            for ticket in sorted(
                tickets, key=lambda item: item["created_at"], reverse=True
            )
        ]

    def get_internal_ticket_with_messages_and_audit_logs(
        self, ticket_id: str
    ) -> dict[str, Any] | None:
        data = self.store.read()
        ticket = self._find_one_in_data(
            data, "tickets", lambda item: item["id"] == ticket_id
        )
        if ticket is None:
            return None

        bundle = self._internal_ticket_bundle(data, ticket)
        bundle["messages"] = sorted(
            [
                message
                for message in data["messages"]
                if message["ticket_id"] == ticket_id
            ],
            key=lambda message: message["sent_at"],
        )
        bundle["audit_logs"] = sorted(
            [
                self._audit_log_bundle(data, audit_log)
                for audit_log in data["audit_logs"]
                if audit_log["ticket_id"] == ticket_id
                or (
                    audit_log["target_type"] == "ticket"
                    and audit_log["target_id"] == ticket_id
                )
            ],
            key=lambda item: item["audit_log"]["occurred_at"],
            reverse=True,
        )
        return bundle

    def assign_internal_ticket(
        self,
        *,
        ticket_id: str,
        assignee_user_id: str,
        actor_user: dict[str, Any],
    ) -> dict[str, Any] | str:
        timestamp = utc_now()

        def save(data: dict[str, Any]) -> dict[str, Any] | str:
            ticket = self._find_one_in_data(
                data, "tickets", lambda item: item["id"] == ticket_id
            )
            if ticket is None:
                return "not_found"
            if ticket["status"] == "closed":
                return "closed"

            assignee = self._find_one_in_data(
                data,
                "users",
                lambda item: item["id"] == assignee_user_id
                and item["role"] == UserRole.AGENT.value
                and item["status"] == UserStatus.ACTIVE.value,
            )
            if assignee is None:
                return "invalid_assignee"

            before = ticket["assignee_user_id"]
            ticket["assignee_user_id"] = assignee_user_id
            ticket["updated_at"] = timestamp
            action = (
                AuditAction.TICKET_ASSIGNED
                if before is None
                else AuditAction.TICKET_REASSIGNED
            )
            data["audit_logs"].append(
                audit_log_record(
                    action=action,
                    actor_user=actor_user,
                    target_type="ticket",
                    target_id=ticket_id,
                    ticket_id=ticket_id,
                    changes={
                        "assignee_user_id": {
                            "before": before,
                            "after": assignee_user_id,
                        }
                    },
                    now=timestamp,
                )
            )
            return self._internal_ticket_bundle(data, ticket)

        return self.store.transaction(save)

    def add_internal_ticket_message(
        self,
        *,
        ticket_id: str,
        sender_user: dict[str, Any],
        content: str,
    ) -> dict[str, Any] | str:
        timestamp = utc_now()

        def save(data: dict[str, Any]) -> dict[str, Any] | str:
            ticket = self._find_one_in_data(
                data, "tickets", lambda item: item["id"] == ticket_id
            )
            if ticket is None:
                return "not_found"
            if ticket["status"] == "closed":
                return "closed"
            if (
                sender_user["role"] == UserRole.AGENT.value
                and ticket["assignee_user_id"] != sender_user["id"]
            ):
                return "forbidden"

            record = message_record(
                ticket_id=ticket_id,
                sender_user=sender_user,
                content=content,
                now=timestamp,
            )
            data["messages"].append(record)
            ticket["updated_at"] = timestamp
            return record

        return self.store.transaction(save)

    def update_internal_ticket_status(
        self,
        *,
        ticket_id: str,
        ticket_status: TicketStatus,
        actor_user: dict[str, Any],
    ) -> dict[str, Any] | str:
        timestamp = utc_now()

        def save(data: dict[str, Any]) -> dict[str, Any] | str:
            ticket = self._find_one_in_data(
                data, "tickets", lambda item: item["id"] == ticket_id
            )
            if ticket is None:
                return "not_found"
            if ticket["status"] == TicketStatus.CLOSED.value:
                return "closed"
            if (
                actor_user["role"] == UserRole.AGENT.value
                and ticket["assignee_user_id"] != actor_user["id"]
            ):
                return "forbidden"

            current_status = TicketStatus(ticket["status"])
            if current_status.next_status() != ticket_status:
                return "invalid_transition"

            before = ticket["status"]
            ticket["status"] = ticket_status.value
            ticket["updated_at"] = timestamp
            data["audit_logs"].append(
                audit_log_record(
                    action=AuditAction.TICKET_STATUS_CHANGED,
                    actor_user=actor_user,
                    target_type="ticket",
                    target_id=ticket_id,
                    ticket_id=ticket_id,
                    changes={
                        "status": {
                            "before": before,
                            "after": ticket_status.value,
                        }
                    },
                    now=timestamp,
                )
            )
            return ticket

        return self.store.transaction(save)

    def add_session(self, session: dict[str, Any]) -> dict[str, Any]:
        def save(data: dict[str, Any]) -> dict[str, Any]:
            if any(
                item["token_hash"] == session["token_hash"]
                for item in data["sessions"]
            ):
                raise ValueError("Session token hash already exists")
            data["sessions"].append(session)
            return session

        return self.store.transaction(save)

    def create_session(
        self, *, token_hash: str, user_id: str, expires_at: str, now: str
    ) -> dict[str, Any]:
        return self.add_session(
            session_record(
                token_hash=token_hash,
                user_id=user_id,
                expires_at=expires_at,
                now=now,
            )
        )

    def get_session_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        return self._find_one(
            "sessions", lambda session: session["token_hash"] == token_hash
        )

    def revoke_session_by_token_hash(self, token_hash: str, revoked_at: str) -> None:
        def revoke(data: dict[str, Any]) -> None:
            for session in data["sessions"]:
                if session["token_hash"] == token_hash:
                    session["revoked_at"] = revoked_at
                    return None
            return None

        self.store.transaction(revoke)

    def touch_session(self, token_hash: str, last_seen_at: str) -> None:
        def touch(data: dict[str, Any]) -> None:
            for session in data["sessions"]:
                if session["token_hash"] == token_hash:
                    session["last_seen_at"] = last_seen_at
                    return None
            return None

        self.store.transaction(touch)

    def _find_one(self, collection: str, predicate) -> dict[str, Any] | None:
        for item in self.store.read()[collection]:
            if predicate(item):
                return item
        return None

    def _find_one_in_data(
        self, data: dict[str, Any], collection: str, predicate
    ) -> dict[str, Any] | None:
        for item in data[collection]:
            if predicate(item):
                return item
        return None

    def _user_by_id_in_data(
        self, data: dict[str, Any], user_id: str | None
    ) -> dict[str, Any] | None:
        if user_id is None:
            return None
        return self._find_one_in_data(data, "users", lambda item: item["id"] == user_id)

    def _internal_ticket_bundle(
        self, data: dict[str, Any], ticket: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "ticket": ticket,
            "customer": self._user_by_id_in_data(data, ticket["customer_user_id"]),
            "assignee": self._user_by_id_in_data(data, ticket["assignee_user_id"]),
            "messages": [],
            "audit_logs": [],
        }

    def _audit_log_bundle(
        self, data: dict[str, Any], audit_log: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "audit_log": audit_log,
            "actor": self._user_by_id_in_data(data, audit_log["actor_user_id"]),
        }

    def _assert_unique_user_identifiers(
        self, data: dict[str, Any], username: str, email: str
    ) -> None:
        for user in data["users"]:
            if user["username"] == username:
                raise ValueError("Username already exists")
            if user["email"] == email:
                raise ValueError("Email already exists")

    def _assert_unique_category_name(self, data: dict[str, Any], name: str) -> None:
        for category in data["categories"]:
            if category["name"] == name:
                raise ValueError("Category name already exists")
