from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config import Settings
from app.domain.enums import UserRole
from app.security.passwords import PasswordService


class AdminInitStatus(str, Enum):
    CREATED = "created"
    ALREADY_EXISTS = "already_exists"
    MISSING_CONFIG = "missing_config"


@dataclass(frozen=True)
class AdminInitResult:
    status: AdminInitStatus
    user: dict[str, Any] | None = None


class AdminInitializer:
    def __init__(self, repository, password_service: PasswordService):
        self.repository = repository
        self.password_service = password_service

    def initialize_if_needed(self, settings: Settings) -> AdminInitResult:
        if self.repository.has_admin():
            return AdminInitResult(status=AdminInitStatus.ALREADY_EXISTS)
        if not settings.initial_admin_configured:
            return AdminInitResult(status=AdminInitStatus.MISSING_CONFIG)

        admin = self.repository.add_user(
            username=settings.initial_admin_username,
            email=settings.initial_admin_email,
            password_hash=self.password_service.hash_password(
                settings.initial_admin_password
            ),
            role=UserRole.ADMIN,
        )
        return AdminInitResult(status=AdminInitStatus.CREATED, user=admin)
