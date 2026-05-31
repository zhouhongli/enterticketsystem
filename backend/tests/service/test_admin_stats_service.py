from app.domain.enums import AuditAction, TicketStatus, UserRole
from app.domain.models import audit_log_record
from app.repositories.json_repository import JsonRepository
from app.storage.json_store import JsonFileStore


def make_repo(tmp_path) -> JsonRepository:
    return JsonRepository(JsonFileStore(tmp_path / "store.json"))


def add_user(repo, *, username, email, role, password_hash="hash"):
    return repo.add_user(
        username=username, email=email, password_hash=password_hash, role=role
    )


def test_list_audit_logs_returns_sorted_desc(tmp_path) -> None:
    repo = make_repo(tmp_path)
    admin = add_user(repo, username="admin", email="a@b.com", role=UserRole.ADMIN)

    # Insert two audit logs out of order
    repo.store.transaction(
        lambda data: data["audit_logs"].append(
            audit_log_record(
                action=AuditAction.TICKET_CREATED,
                actor_user=admin,
                target_type="ticket",
                target_id="t1",
                changes={"status": {"before": None, "after": "unassigned"}},
                ticket_id="t1",
                now="2026-05-31T12:00:00Z",
            )
        )
    )
    repo.store.transaction(
        lambda data: data["audit_logs"].append(
            audit_log_record(
                action=AuditAction.TICKET_STATUS_CHANGED,
                actor_user=admin,
                target_type="ticket",
                target_id="t1",
                changes={"status": {"before": "unassigned", "after": "processing"}},
                ticket_id="t1",
                now="2026-05-31T10:00:00Z",
            )
        )
    )

    logs = repo.list_audit_logs()
    assert len(logs) == 2
    assert logs[0]["action"] == "ticket_created"  # newer first
    assert logs[1]["action"] == "ticket_status_changed"


def test_empty_data_returns_zeros(tmp_path) -> None:
    from app.services.admin_stats_service import AdminStatsService

    svc = AdminStatsService(make_repo(tmp_path))
    result = svc.get_stats("7d")

    assert result["overview"]["total"] == 0
    assert result["overview"]["by_status"] == {
        "unassigned": 0,
        "processing": 0,
        "resolved": 0,
        "closed": 0,
    }
    assert result["trend"] == []
    assert result["avg_times"]["overall_avg_hours"] == 0
    assert result["category_dist"] == []
    assert result["agent_workload"] == []
    assert result["recent_logs"] == []


def test_full_scenario_returns_all_sections(tmp_path) -> None:
    """Create tickets, audit logs, and verify all stats sections populate."""
    from app.services.admin_stats_service import AdminStatsService

    repo = make_repo(tmp_path)
    admin = add_user(repo, username="admin", email="a@b.com", role=UserRole.ADMIN)
    agent = add_user(repo, username="agent01", email="g@b.com", role=UserRole.AGENT)
    customer = add_user(repo, username="cust01", email="c@b.com", role=UserRole.CUSTOMER)
    cat = repo.create_category(name="产品故障", actor_user=admin)

    # Create a ticket
    ticket = repo.create_customer_ticket(
        category_id=cat["id"],
        title="测试工单",
        description="描述",
        customer_user=customer,
    )

    # Assign it
    repo.assign_internal_ticket(
        ticket_id=ticket["id"], assignee_user_id=agent["id"], actor_user=admin
    )

    # Move to processing
    repo.update_internal_ticket_status(
        ticket_id=ticket["id"],
        ticket_status=TicketStatus.PROCESSING,
        actor_user=agent,
    )

    svc = AdminStatsService(repo)
    result = svc.get_stats("7d")

    assert result["overview"]["total"] == 1
    assert result["overview"]["by_status"]["processing"] == 1
    assert len(result["trend"]) == 1
    assert result["trend"][0]["count"] == 1
    assert len(result["category_dist"]) == 1
    assert result["category_dist"][0]["name"] == "产品故障"
    assert result["category_dist"][0]["count"] == 1
    assert len(result["agent_workload"]) == 1
    assert result["agent_workload"][0]["username"] == "agent01"
    assert result["agent_workload"][0]["assigned"] == 1
    assert len(result["recent_logs"]) >= 3  # created, assigned, status_changed
