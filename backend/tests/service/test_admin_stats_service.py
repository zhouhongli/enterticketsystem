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


def test_avg_times_for_closed_ticket(tmp_path) -> None:
    """Verify avg_times computes non-zero overall_avg_hours for a full ticket lifecycle."""
    from app.domain.models import ticket_record
    from app.services.admin_stats_service import AdminStatsService

    repo = make_repo(tmp_path)
    admin = add_user(repo, username="admin", email="a@b.com", role=UserRole.ADMIN)
    agent = add_user(repo, username="agent01", email="g@b.com", role=UserRole.AGENT)
    customer = add_user(repo, username="cust01", email="c@b.com", role=UserRole.CUSTOMER)
    cat = repo.create_category(name="产品故障", actor_user=admin)

    # Create a ticket with a fixed timestamp
    tid = "lifecycle-ticket-001"
    repo.store.transaction(
        lambda data: data["tickets"].append(
            ticket_record(
                title="生命周期工单",
                description="描述",
                category=cat,
                customer_user_id=customer["id"],
                ticket_id=tid,
                now="2026-05-31T00:00:00Z",
            )
        )
    )

    # Inject a full lifecycle with spaced-out timestamps
    for action, changes, occurred_at in [
        (
            AuditAction.TICKET_CREATED,
            {"status": {"before": None, "after": "unassigned"}},
            "2026-05-31T00:00:00Z",
        ),
        (
            AuditAction.TICKET_ASSIGNED,
            {"assignee_user_id": {"before": None, "after": agent["id"]}},
            "2026-05-31T02:00:00Z",
        ),
        (
            AuditAction.TICKET_STATUS_CHANGED,
            {"status": {"before": "unassigned", "after": "processing"}},
            "2026-05-31T04:00:00Z",
        ),
        (
            AuditAction.TICKET_STATUS_CHANGED,
            {"status": {"before": "processing", "after": "resolved"}},
            "2026-05-31T10:00:00Z",
        ),
        (
            AuditAction.TICKET_STATUS_CHANGED,
            {"status": {"before": "resolved", "after": "closed"}},
            "2026-06-01T00:00:00Z",
        ),
    ]:
        repo.store.transaction(
            lambda data: data["audit_logs"].append(
                audit_log_record(
                    action=action,
                    actor_user=admin,
                    target_type="ticket",
                    target_id=tid,
                    changes=changes,
                    ticket_id=tid,
                    now=occurred_at,
                )
            )
        )

    svc = AdminStatsService(repo)
    result = svc.get_stats("7d")

    assert result["avg_times"]["overall_avg_hours"] > 0


def test_all_range_returns_weekly_buckets(tmp_path) -> None:
    """Verify that range_='all' groups tickets by week."""
    from datetime import datetime, timedelta, timezone

    from app.domain.models import ticket_record
    from app.services.admin_stats_service import AdminStatsService

    repo = make_repo(tmp_path)
    admin = add_user(repo, username="admin", email="a@b.com", role=UserRole.ADMIN)
    customer = add_user(repo, username="cust01", email="c@b.com", role=UserRole.CUSTOMER)
    cat = repo.create_category(name="产品故障", actor_user=admin)

    # Inject two tickets on different days but in the same week (2026-05-18 is Monday)
    for i, (title, created_at) in enumerate([
        ("工单周一", "2026-05-18T10:00:00Z"),
        ("工单周三", "2026-05-20T10:00:00Z"),
    ], start=1):
        tid = f"weekly-ticket-00{i}"
        repo.store.transaction(
            lambda data: data["tickets"].append(
                ticket_record(
                    title=title,
                    description="描述",
                    category=cat,
                    customer_user_id=customer["id"],
                    ticket_id=tid,
                    now=created_at,
                )
            )
        )

    svc = AdminStatsService(repo)
    result = svc.get_stats(range_="all")

    # Both tickets should be in the same weekly bucket
    assert len(result["trend"]) == 1
    assert result["trend"][0]["count"] == 2
    # The bucket key should be the Monday of that week
    week_start = datetime(2026, 5, 18, tzinfo=timezone.utc)
    assert result["trend"][0]["date"] == week_start.strftime("%Y-%m-%d")
