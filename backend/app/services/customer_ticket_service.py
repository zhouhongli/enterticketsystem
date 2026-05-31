from __future__ import annotations

from fastapi import status

from app.api.errors import raise_api_error
from app.repositories.json_repository import JsonRepository
from app.schemas.tickets import (
    CustomerTicketCreateRequest,
    CustomerTicketMessageCreateRequest,
    customer_ticket_detail_response,
    customer_ticket_detail_with_messages_response,
    customer_ticket_list_item_response,
    message_response,
)


class CustomerTicketService:
    def __init__(self, repository: JsonRepository) -> None:
        self.repository = repository

    def create_ticket(
        self, request: CustomerTicketCreateRequest, customer_user: dict
    ) -> dict:
        ticket = self.repository.create_customer_ticket(
            category_id=request.category_id,
            title=request.title,
            description=request.description,
            customer_user=customer_user,
        )
        if ticket is None:
            raise_api_error(
                code="CONFLICT",
                message="分类不存在或已停用。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return customer_ticket_detail_response(ticket)

    def list_tickets(self, customer_user: dict) -> dict:
        tickets = self.repository.list_customer_tickets(customer_user["id"])
        return {
            "items": [
                customer_ticket_list_item_response(ticket) for ticket in tickets
            ]
        }

    def get_ticket(self, ticket_id: str, customer_user: dict) -> dict:
        result = self.repository.get_customer_ticket_with_messages(
            ticket_id=ticket_id,
            customer_user_id=customer_user["id"],
        )
        if result is None:
            raise_api_error(
                code="RESOURCE_NOT_FOUND",
                message="工单不存在。",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return customer_ticket_detail_with_messages_response(
            result["ticket"], result["messages"]
        )

    def add_message(
        self,
        ticket_id: str,
        request: CustomerTicketMessageCreateRequest,
        customer_user: dict,
    ) -> dict:
        result = self.repository.add_customer_ticket_message(
            ticket_id=ticket_id,
            customer_user=customer_user,
            content=request.content,
        )
        if result == "not_found":
            raise_api_error(
                code="RESOURCE_NOT_FOUND",
                message="工单不存在。",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if result == "closed":
            raise_api_error(
                code="CONFLICT",
                message="工单已关闭，不能继续留言。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return message_response(result)
