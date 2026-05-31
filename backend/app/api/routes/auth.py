from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.dependencies import (
    get_current_user,
    get_repository,
    get_session_service,
)
from app.config import Settings, get_settings
from app.repositories.json_repository import JsonRepository
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    current_user_response,
)
from app.security.passwords import PasswordService
from app.security.sessions import SessionService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(
    repository: JsonRepository = Depends(get_repository),
    session_service: SessionService = Depends(get_session_service),
) -> AuthService:
    return AuthService(repository, PasswordService(), session_service)


def set_session_cookie(
    response: Response, settings: Settings, raw_token: str
) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_hours * 60 * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.session_cookie_name, path="/")


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    return service.register_customer(request)


@router.post("/login")
def login(
    request: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
    service: AuthService = Depends(get_auth_service),
) -> dict:
    result = service.login(request)
    set_session_cookie(response, settings, result.session.raw_token)
    return result.user


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
    current_user: dict = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
) -> dict[str, bool]:
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        session_service.revoke_session(raw_token)
    clear_session_cookie(response, settings)
    return {"success": True}


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)) -> dict:
    return current_user_response(current_user)
