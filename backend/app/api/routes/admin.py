from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies import get_repository, require_admin
from app.api.errors import raise_api_error
from app.repositories.json_repository import JsonRepository
from app.schemas.users import AgentCreateRequest, CustomerStatusUpdateRequest
from app.security.passwords import PasswordService
from app.services.admin_stats_service import AdminStatsService, RANGE_DAYS
from app.services.user_admin_service import UserAdminService

router = APIRouter(prefix="/admin", tags=["admin"])


def get_user_admin_service(
    repository: JsonRepository = Depends(get_repository),
) -> UserAdminService:
    return UserAdminService(repository, PasswordService())


@router.get("/agents")
def list_agents(
    current_user: dict = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> dict:
    return service.list_agents()


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def create_agent(
    request: AgentCreateRequest,
    current_user: dict = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> dict:
    return service.create_agent(request)


@router.get("/customers")
def list_customers(
    current_user: dict = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> dict:
    return service.list_customers()


@router.patch("/customers/{customer_id}/status")
def update_customer_status(
    customer_id: str,
    request: CustomerStatusUpdateRequest,
    current_user: dict = Depends(require_admin),
    service: UserAdminService = Depends(get_user_admin_service),
) -> dict:
    return service.update_customer_status(customer_id, request, current_user)


def get_admin_stats_service(
    repository: JsonRepository = Depends(get_repository),
) -> AdminStatsService:
    return AdminStatsService(repository)


@router.get("/stats")
def get_stats(
    range_: str = Query(default="7d", alias="range"),
    current_user: dict = Depends(require_admin),
    service: AdminStatsService = Depends(get_admin_stats_service),
) -> dict:
    if range_ not in RANGE_DAYS and range_ != "all":
        raise_api_error(
            code="VALIDATION_ERROR",
            message="无效的时间范围参数，请使用 7d、30d、90d 或 all。",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return service.get_stats(range_)
