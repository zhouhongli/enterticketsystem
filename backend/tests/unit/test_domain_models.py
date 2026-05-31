from app.domain.enums import (
    AuditAction,
    CategoryStatus,
    TicketStatus,
    UserRole,
    UserStatus,
)
from app.domain.models import new_id, utc_now


def test_confirmed_enum_values_match_baseline() -> None:
    assert UserRole.CUSTOMER.value == "customer"
    assert UserRole.AGENT.value == "agent"
    assert UserRole.ADMIN.value == "admin"
    assert UserStatus.ACTIVE.value == "active"
    assert UserStatus.DISABLED.value == "disabled"
    assert CategoryStatus.ACTIVE.value == "active"
    assert CategoryStatus.INACTIVE.value == "inactive"
    assert TicketStatus.UNASSIGNED.value == "unassigned"
    assert TicketStatus.PROCESSING.value == "processing"
    assert TicketStatus.RESOLVED.value == "resolved"
    assert TicketStatus.CLOSED.value == "closed"
    assert AuditAction.TICKET_CREATED.value == "ticket_created"
    assert AuditAction.CUSTOMER_STATUS_CHANGED.value == "customer_status_changed"


def test_ticket_status_transitions_are_linear() -> None:
    assert TicketStatus.UNASSIGNED.next_status() == TicketStatus.PROCESSING
    assert TicketStatus.PROCESSING.next_status() == TicketStatus.RESOLVED
    assert TicketStatus.RESOLVED.next_status() == TicketStatus.CLOSED
    assert TicketStatus.CLOSED.next_status() is None


def test_generated_ids_and_times_are_stable_storage_formats() -> None:
    assert len(new_id()) == 36
    assert utc_now().endswith("Z")
