from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from app.domain.enums import UserStatus
from app.domain.models import format_utc, parse_utc, utc_now


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CreatedSession:
    raw_token: str
    session: dict[str, Any]


class SessionService:
    def __init__(self, repository, ttl_hours: int):
        self.repository = repository
        self.ttl_hours = ttl_hours

    def create_session(self, user_id: str, now: str | None = None) -> CreatedSession:
        raw_token = secrets.token_urlsafe(32)
        created_at = now or utc_now()
        expires_at = format_utc(
            parse_utc(created_at) + timedelta(hours=self.ttl_hours)
        )
        session = self.repository.create_session(
            token_hash=hash_session_token(raw_token),
            user_id=user_id,
            expires_at=expires_at,
            now=created_at,
        )
        return CreatedSession(raw_token=raw_token, session=session)

    def authenticate(self, raw_token: str, now: str | None = None) -> dict | None:
        token_hash = hash_session_token(raw_token)
        session = self.repository.get_session_by_token_hash(token_hash)
        if session is None:
            return None

        current_time = now or utc_now()
        if session.get("revoked_at") is not None:
            return None
        if parse_utc(session["expires_at"]) <= parse_utc(current_time):
            self.repository.revoke_session_by_token_hash(token_hash, current_time)
            return None

        user = self.repository.get_user(session["user_id"])
        if user is None or user["status"] != UserStatus.ACTIVE.value:
            self.repository.revoke_session_by_token_hash(token_hash, current_time)
            return None

        self.repository.touch_session(token_hash, current_time)
        return user

    def revoke_session(self, raw_token: str, now: str | None = None) -> None:
        self.repository.revoke_session_by_token_hash(
            hash_session_token(raw_token), now or utc_now()
        )
