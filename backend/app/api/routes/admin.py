from fastapi import APIRouter, Depends, status

from app.api.dependencies import get_repository, require_admin
from app.repositories.json_repository import JsonRepository
from app.schemas.users import AgentCreateRequest, CustomerStatusUpdateRequest
from app.security.passwords import PasswordService
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
