from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status

from app.api.dependencies import (
    get_current_user,
    get_repository,
    require_admin,
    require_customer,
)
from app.repositories.json_repository import JsonRepository
from app.schemas.categories import (
    CategoryCreateRequest,
    CategoryStatusUpdateRequest,
    CategoryUpdateRequest,
)
from app.services.category_service import CategoryService


router = APIRouter(tags=["categories"])


def get_category_service(
    repository: JsonRepository = Depends(get_repository),
) -> CategoryService:
    return CategoryService(repository)


def require_category_customer(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return require_customer(current_user)


def require_category_admin(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    return require_admin(current_user)


@router.get("/categories/active")
def list_active_categories(
    _current_user: Dict[str, Any] = Depends(require_category_customer),
    service: CategoryService = Depends(get_category_service),
) -> Dict[str, List[Dict[str, str]]]:
    return service.list_active_categories()


@router.get("/admin/categories")
def list_admin_categories(
    _current_user: Dict[str, Any] = Depends(require_category_admin),
    service: CategoryService = Depends(get_category_service),
) -> Dict[str, List[Dict[str, str]]]:
    return service.list_admin_categories()


@router.post("/admin/categories", status_code=status.HTTP_201_CREATED)
def create_category(
    request: CategoryCreateRequest,
    current_user: Dict[str, Any] = Depends(require_category_admin),
    service: CategoryService = Depends(get_category_service),
) -> Dict[str, str]:
    return service.create_category(request, actor_user=current_user)


@router.patch("/admin/categories/{category_id}")
def update_category_name(
    category_id: str,
    request: CategoryUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_category_admin),
    service: CategoryService = Depends(get_category_service),
) -> Dict[str, str]:
    return service.update_category_name(
        category_id=category_id,
        request=request,
        actor_user=current_user,
    )


@router.patch("/admin/categories/{category_id}/status")
def update_category_status(
    category_id: str,
    request: CategoryStatusUpdateRequest,
    current_user: Dict[str, Any] = Depends(require_category_admin),
    service: CategoryService = Depends(get_category_service),
) -> Dict[str, str]:
    return service.update_category_status(
        category_id=category_id,
        request=request,
        actor_user=current_user,
    )
