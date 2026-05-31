from __future__ import annotations

from typing import Protocol

from app.domain.enums import UserRole, UserStatus


class UserRepository(Protocol):
    def list_users(self) -> list[dict]:
        ...

    def get_user(self, user_id: str) -> dict | None:
        ...

    def add_user(
        self,
        *,
        username: str,
        email: str,
        password_hash: str,
        role: UserRole,
        status: UserStatus = UserStatus.ACTIVE,
    ) -> dict:
        ...

    def has_admin(self) -> bool:
        ...


class SessionRepository(Protocol):
    def add_session(self, session: dict) -> dict:
        ...

    def get_session_by_token_hash(self, token_hash: str) -> dict | None:
        ...

    def revoke_session_by_token_hash(self, token_hash: str, revoked_at: str) -> None:
        ...

    def touch_session(self, token_hash: str, last_seen_at: str) -> None:
        ...
