from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class CategoryStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class TicketStatus(str, Enum):
    UNASSIGNED = "unassigned"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    CLOSED = "closed"

    def next_status(self) -> "TicketStatus | None":
        transitions = {
            TicketStatus.UNASSIGNED: TicketStatus.PROCESSING,
            TicketStatus.PROCESSING: TicketStatus.RESOLVED,
            TicketStatus.RESOLVED: TicketStatus.CLOSED,
        }
        return transitions.get(self)


class AuditAction(str, Enum):
    TICKET_CREATED = "ticket_created"
    TICKET_ASSIGNED = "ticket_assigned"
    TICKET_REASSIGNED = "ticket_reassigned"
    TICKET_STATUS_CHANGED = "ticket_status_changed"
    CATEGORY_CREATED = "category_created"
    CATEGORY_UPDATED = "category_updated"
    CATEGORY_STATUS_CHANGED = "category_status_changed"
    CUSTOMER_STATUS_CHANGED = "customer_status_changed"
