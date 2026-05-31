from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NoReturn

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.storage.json_store import StorageError


@dataclass(frozen=True)
class ApiError:
    code: str
    message: str
    status_code: int
    field_errors: dict[str, str] | None = None


class ApiErrorException(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        self.error = ApiError(
            code=code,
            message=message,
            status_code=status_code,
            field_errors=field_errors,
        )


def raise_api_error(
    *,
    code: str,
    message: str,
    status_code: int,
    field_errors: dict[str, str] | None = None,
) -> NoReturn:
    raise ApiErrorException(
        code=code,
        message=message,
        status_code=status_code,
        field_errors=field_errors,
    )


def error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    field_errors: dict[str, str] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if field_errors is not None:
        payload["error"]["field_errors"] = field_errors
    return JSONResponse(status_code=status_code, content=payload)


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiErrorException)
    async def handle_api_error(
        request: Request, exc: ApiErrorException
    ) -> JSONResponse:
        response = error_response(
            code=exc.error.code,
            message=exc.error.message,
            status_code=exc.error.status_code,
            field_errors=exc.error.field_errors,
        )
        cookie_name = getattr(request.state, "clear_session_cookie_name", None)
        if cookie_name:
            response.delete_cookie(cookie_name, path="/")
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors: dict[str, str] = {}
        for error in exc.errors():
            location = [str(item) for item in error.get("loc", [])]
            field = location[-1] if location else "request"
            field_errors[field] = str(error.get("msg", "字段校验失败。"))
        return error_response(
            code="VALIDATION_ERROR",
            message="请求字段不符合要求。",
            status_code=422,
            field_errors=field_errors,
        )

    @app.exception_handler(StorageError)
    async def handle_storage_error(request: Request, exc: StorageError) -> JSONResponse:
        return error_response(
            code="STORAGE_ERROR",
            message="数据保存失败，请稍后重试。",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            return error_response(
                code="RESOURCE_NOT_FOUND",
                message="资源不存在。",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return error_response(
            code="HTTP_ERROR",
            message=str(exc.detail),
            status_code=exc.status_code,
        )
