from __future__ import annotations

from typing import Any

from fastapi import status

from app.api.errors import raise_api_error
from app.repositories.json_repository import JsonRepository
from app.schemas.categories import (
    CategoryCreateRequest,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
    active_category_response,
    admin_category_response,
)


class CategoryService:
    def __init__(self, repository: JsonRepository) -> None:
        self.repository = repository

    def list_active_categories(self) -> dict[str, list[dict[str, str]]]:
        return {
            "items": [
                active_category_response(category)
                for category in self.repository.list_active_categories()
            ]
        }

    def list_admin_categories(self) -> dict[str, list[dict[str, str]]]:
        return {
            "items": [
                admin_category_response(category)
                for category in self.repository.list_categories()
            ]
        }

    def create_category(
        self, request: CategoryCreateRequest, actor_user: dict[str, Any]
    ) -> dict[str, str]:
        try:
            category = self.repository.create_category(
                name=request.name,
                actor_user=actor_user,
            )
        except ValueError:
            raise_api_error(
                code="CONFLICT",
                message="分类名称已经存在。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return admin_category_response(category)

    def update_category_name(
        self,
        category_id: str,
        request: CategoryUpdateRequest,
        actor_user: dict[str, Any],
    ) -> dict[str, str]:
        try:
            category = self.repository.update_category_name(
                category_id=category_id,
                name=request.name,
                actor_user=actor_user,
            )
        except ValueError:
            raise_api_error(
                code="CONFLICT",
                message="分类名称已经存在。",
                status_code=status.HTTP_409_CONFLICT,
            )

        if category is None:
            self._raise_category_not_found()
        return admin_category_response(category)

    def update_category_status(
        self,
        category_id: str,
        request: CategoryStatusUpdateRequest,
        actor_user: dict[str, Any],
    ) -> dict[str, str]:
        category = self.repository.update_category_status(
            category_id=category_id,
            status=request.status,
            actor_user=actor_user,
        )

        if category is None:
            self._raise_category_not_found()
        return admin_category_response(category)

    def _raise_category_not_found(self) -> None:
        raise_api_error(
            code="RESOURCE_NOT_FOUND",
            message="分类不存在。",
            status_code=status.HTTP_404_NOT_FOUND,
        )
