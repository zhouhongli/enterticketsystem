from __future__ import annotations

from fastapi import status

from app.api.errors import raise_api_error
from app.domain.enums import UserRole
from app.repositories.json_repository import JsonRepository
from app.schemas.users import (
    AgentCreateRequest,
    CustomerStatusUpdateRequest,
    agent_response,
    customer_response,
)
from app.security.passwords import PasswordService


class UserAdminService:
    def __init__(
        self, repository: JsonRepository, password_service: PasswordService
    ) -> None:
        self.repository = repository
        self.password_service = password_service

    def list_agents(self) -> dict:
        return {
            "items": [
                agent_response(user)
                for user in self.repository.list_users_by_role(UserRole.AGENT)
            ]
        }

    def create_agent(self, request: AgentCreateRequest) -> dict:
        try:
            user = self.repository.add_user(
                username=request.username,
                email=request.email,
                password_hash=self.password_service.hash_password(request.password),
                role=UserRole.AGENT,
            )
        except ValueError:
            raise_api_error(
                code="CONFLICT",
                message="用户名或邮箱已经存在。",
                status_code=status.HTTP_409_CONFLICT,
            )
        return agent_response(user)

    def list_customers(self) -> dict:
        return {
            "items": [
                customer_response(user)
                for user in self.repository.list_users_by_role(UserRole.CUSTOMER)
            ]
        }

    def update_customer_status(
        self,
        customer_id: str,
        request: CustomerStatusUpdateRequest,
        actor_user: dict,
    ) -> dict:
        try:
            user = self.repository.update_customer_status(
                user_id=customer_id,
                status=request.status,
                actor_user=actor_user,
            )
        except ValueError:
            raise_api_error(
                code="CONFLICT",
                message="目标用户不是客户账号。",
                status_code=status.HTTP_409_CONFLICT,
            )

        if user is None:
            raise_api_error(
                code="RESOURCE_NOT_FOUND",
                message="目标客户不存在。",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return customer_response(user)
