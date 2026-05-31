from __future__ import annotations

from typing import Any

from fastapi import Depends, Request, status

from app.api.errors import raise_api_error
from app.config import Settings, get_settings
from app.domain.enums import UserRole
from app.repositories.json_repository import JsonRepository
from app.security.sessions import SessionService
from app.storage.json_store import JsonFileStore


def get_repository(settings: Settings = Depends(get_settings)) -> JsonRepository:
    return JsonRepository(JsonFileStore(settings.data_file_path))


def get_session_service(
    settings: Settings = Depends(get_settings),
    repository: JsonRepository = Depends(get_repository),
) -> SessionService:
    return SessionService(repository, ttl_hours=settings.session_ttl_hours)


def get_current_user(
    request: Request,
    settings: Settings = Depends(get_settings),
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, Any]:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        raise_api_error(
            code="AUTHENTICATION_REQUIRED",
            message="请先登录后再继续操作。",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    user = session_service.authenticate(raw_token)
    if user is None:
        request.state.clear_session_cookie_name = settings.session_cookie_name
        raise_api_error(
            code="AUTHENTICATION_REQUIRED",
            message="登录状态已失效，请重新登录。",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    return user


def require_admin(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["role"] != UserRole.ADMIN.value:
        raise_api_error(
            code="FORBIDDEN",
            message="当前账号无权执行该操作。",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user


def require_customer(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["role"] != UserRole.CUSTOMER.value:
        raise_api_error(
            code="FORBIDDEN",
            message="当前账号无权执行该操作。",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user


def require_internal_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if current_user["role"] not in {UserRole.AGENT.value, UserRole.ADMIN.value}:
        raise_api_error(
            code="FORBIDDEN",
            message="当前账号无权执行该操作。",
            status_code=status.HTTP_403_FORBIDDEN,
        )
    return current_user
