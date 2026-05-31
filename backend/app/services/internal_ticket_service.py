from __future__ import annotations

from fastapi import status

from app.api.errors import raise_api_error
from app.repositories.json_repository import JsonRepository
from app.schemas.tickets import (
    InternalTicketAssignmentRequest,
    InternalTicketMessageCreateRequest,
    InternalTicketStatusUpdateRequest,
    internal_ticket_assignment_response,
    internal_ticket_detail_response,
    internal_ticket_list_item_response,
    internal_ticket_status_response,
    message_response,
)


class InternalTicketService:
    def __init__(self, repository: JsonRepository) -> None:
        self.repository = repository

    def list_tickets(self, ticket_status: str | None = None) -> dict:
        tickets = self.repository.list_internal_tickets(ticket_status)
        return {
            "items": [
                internal_ticket_list_item_response(ticket) for ticket in tickets
            ]
        }

    def get_ticket(self, ticket_id: str) -> dict:
        result = self.repository.get_internal_ticket_with_messages_and_audit_logs(
            ticket_id
        )
        if result is None:
            raise_api_error(
                code="RESOURCE_NOT_FOUND",
                message="工单不存在。",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return internal_ticket_detail_response(result)

    def assign_ticket(
        self,
        ticket_id: str,
        request: InternalTicketAssignmentRequest,
        actor_user: dict,
    ) -> dict:
        result = self.repository.assign_internal_ticket(
            ticket_id=ticket_id,
            assignee_user_id=request.assignee_user_id,
            actor_user=actor_user,
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
                message="工单已关闭，不能重新分配。",
                status_code=status.HTTP_409_CONFLICT,
            )
        if result == "invalid_assignee":
            raise_api_error(
                code="CONFLICT",
                message="目标负责人不是有效客服账号。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return internal_ticket_assignment_response(result)

    def add_message(
        self,
        ticket_id: str,
        request: InternalTicketMessageCreateRequest,
        current_user: dict,
    ) -> dict:
        result = self.repository.add_internal_ticket_message(
            ticket_id=ticket_id,
            sender_user=current_user,
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
        if result == "forbidden":
            raise_api_error(
                code="FORBIDDEN",
                message="当前账号无权执行该操作。",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        return message_response(result)

    def update_status(
        self,
        ticket_id: str,
        request: InternalTicketStatusUpdateRequest,
        current_user: dict,
    ) -> dict:
        result = self.repository.update_internal_ticket_status(
            ticket_id=ticket_id,
            ticket_status=request.status,
            actor_user=current_user,
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
                message="工单已关闭，不能继续变更状态。",
                status_code=status.HTTP_409_CONFLICT,
            )
        if result == "forbidden":
            raise_api_error(
                code="FORBIDDEN",
                message="当前账号无权执行该操作。",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        if result == "invalid_transition":
            raise_api_error(
                code="CONFLICT",
                message="状态只能按待分配、处理中、已解决、已关闭顺序推进。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return internal_ticket_status_response(result)
