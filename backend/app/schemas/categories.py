from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import CategoryStatus


class CategoryNameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=50)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class CategoryCreateRequest(CategoryNameRequest):
    pass


class CategoryUpdateRequest(CategoryNameRequest):
    pass


class CategoryStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CategoryStatus


def active_category_response(category: dict[str, Any]) -> dict[str, str]:
    return {
        "id": category["id"],
        "name": category["name"],
    }


def admin_category_response(category: dict[str, Any]) -> dict[str, str]:
    return {
        "id": category["id"],
        "name": category["name"],
        "status": category["status"],
        "created_at": category["created_at"],
        "updated_at": category["updated_at"],
    }
