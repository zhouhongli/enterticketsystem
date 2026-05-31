from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies import get_repository, require_admin, require_internal_user
from app.api.errors import raise_api_error
from app.domain.enums import TicketStatus
from app.repositories.json_repository import JsonRepository
from app.schemas.tickets import (
    InternalTicketAssignmentRequest,
    InternalTicketMessageCreateRequest,
    InternalTicketStatusUpdateRequest,
)
from app.services.internal_ticket_service import InternalTicketService

router = APIRouter(prefix="/internal", tags=["internal"])


def get_internal_ticket_service(
    repository: JsonRepository = Depends(get_repository),
) -> InternalTicketService:
    return InternalTicketService(repository)


def reject_unsupported_query_params(request: Request, allowed: set[str]) -> None:
    if any(key not in allowed for key in request.query_params):
        raise_api_error(
            code="VALIDATION_ERROR",
            message="请求字段不符合要求。",
            status_code=422,
        )


@router.get("/tickets")
def list_tickets(
    request: Request,
    ticket_status: TicketStatus | None = Query(default=None, alias="status"),
    current_user: dict = Depends(require_internal_user),
    service: InternalTicketService = Depends(get_internal_ticket_service),
) -> dict:
    reject_unsupported_query_params(request, {"status"})
    if len(request.query_params.getlist("status")) > 1:
        raise_api_error(
            code="VALIDATION_ERROR",
            message="请求字段不符合要求。",
            status_code=422,
        )
    status_value = ticket_status.value if ticket_status is not None else None
    return service.list_tickets(status_value)


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    current_user: dict = Depends(require_internal_user),
    service: InternalTicketService = Depends(get_internal_ticket_service),
) -> dict:
    return service.get_ticket(ticket_id)


@router.patch("/tickets/{ticket_id}/assignment")
def assign_ticket(
    ticket_id: str,
    request: InternalTicketAssignmentRequest,
    current_user: dict = Depends(require_admin),
    service: InternalTicketService = Depends(get_internal_ticket_service),
) -> dict:
    return service.assign_ticket(ticket_id, request, current_user)


@router.post("/tickets/{ticket_id}/messages", status_code=201)
def add_message(
    ticket_id: str,
    request: InternalTicketMessageCreateRequest,
    current_user: dict = Depends(require_internal_user),
    service: InternalTicketService = Depends(get_internal_ticket_service),
) -> dict:
    return service.add_message(ticket_id, request, current_user)


@router.patch("/tickets/{ticket_id}/status")
def update_status(
    ticket_id: str,
    request: InternalTicketStatusUpdateRequest,
    current_user: dict = Depends(require_internal_user),
    service: InternalTicketService = Depends(get_internal_ticket_service),
) -> dict:
    return service.update_status(ticket_id, request, current_user)
