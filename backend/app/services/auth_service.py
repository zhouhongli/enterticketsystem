from __future__ import annotations

from dataclasses import dataclass

from fastapi import status

from app.api.errors import raise_api_error
from app.domain.enums import UserRole, UserStatus
from app.repositories.json_repository import JsonRepository
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    current_user_response,
    registered_user_response,
)
from app.security.passwords import PasswordService
from app.security.sessions import CreatedSession, SessionService


@dataclass(frozen=True)
class LoginResult:
    user: dict
    session: CreatedSession


class AuthService:
    def __init__(
        self,
        repository: JsonRepository,
        password_service: PasswordService,
        session_service: SessionService,
    ) -> None:
        self.repository = repository
        self.password_service = password_service
        self.session_service = session_service

    def register_customer(self, request: RegisterRequest) -> dict:
        try:
            user = self.repository.add_user(
                username=request.username,
                email=request.email,
                password_hash=self.password_service.hash_password(request.password),
                role=UserRole.CUSTOMER,
            )
        except ValueError:
            raise_api_error(
                code="CONFLICT",
                message="用户名或邮箱已经存在。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return registered_user_response(user)

    def login(self, request: LoginRequest) -> LoginResult:
        user = self._find_login_user(request.identifier)
        if (
            user is None
            or user["status"] != UserStatus.ACTIVE.value
            or not self.password_service.verify_password(
                request.password, user["password_hash"]
            )
        ):
            raise_api_error(
                code="LOGIN_FAILED",
                message="账号或密码错误，或账号不可用。",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        return LoginResult(
            user=current_user_response(user),
            session=self.session_service.create_session(user["id"]),
        )

    def _find_login_user(self, identifier: str) -> dict | None:
        if "@" in identifier:
            return self.repository.get_user_by_email(identifier)
        return self.repository.get_user_by_username(identifier)
