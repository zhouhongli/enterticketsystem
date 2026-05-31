from fastapi import APIRouter, Depends, Request, status

from app.api.errors import raise_api_error
from app.api.dependencies import get_repository, require_customer
from app.repositories.json_repository import JsonRepository
from app.schemas.tickets import (
    CustomerTicketCreateRequest,
    CustomerTicketMessageCreateRequest,
)
from app.services.customer_ticket_service import CustomerTicketService

router = APIRouter(prefix="/customer", tags=["customer"])


def get_customer_ticket_service(
    repository: JsonRepository = Depends(get_repository),
) -> CustomerTicketService:
    return CustomerTicketService(repository)


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(
    request: CustomerTicketCreateRequest,
    current_user: dict = Depends(require_customer),
    service: CustomerTicketService = Depends(get_customer_ticket_service),
) -> dict:
    return service.create_ticket(request, current_user)


@router.get("/tickets")
def list_tickets(
    request: Request,
    current_user: dict = Depends(require_customer),
    service: CustomerTicketService = Depends(get_customer_ticket_service),
) -> dict:
    if request.query_params:
        raise_api_error(
            code="VALIDATION_ERROR",
            message="请求字段不符合要求。",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return service.list_tickets(current_user)


@router.get("/tickets/{ticket_id}")
def get_ticket(
    ticket_id: str,
    current_user: dict = Depends(require_customer),
    service: CustomerTicketService = Depends(get_customer_ticket_service),
) -> dict:
    return service.get_ticket(ticket_id, current_user)


@router.post("/tickets/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
def add_message(
    ticket_id: str,
    request: CustomerTicketMessageCreateRequest,
    current_user: dict = Depends(require_customer),
    service: CustomerTicketService = Depends(get_customer_ticket_service),
) -> dict:
    return service.add_message(ticket_id, request, current_user)
