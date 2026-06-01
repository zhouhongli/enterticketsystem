"""Seed script for development/testing. Creates users, categories, tickets, messages, and audit logs."""
from __future__ import annotations

from app.config import get_settings
from app.domain.enums import CategoryStatus, TicketStatus, UserRole, UserStatus
from app.repositories.json_repository import JsonRepository
from app.security.passwords import PasswordService
from app.storage.json_store import JsonFileStore


def seed() -> None:
    settings = get_settings()
    store = JsonFileStore(settings.data_file_path)
    store.ensure_initialized()
    repo = JsonRepository(store)
    pw = PasswordService()

    # ── Users ──
    admin_user = repo.add_user(
        username="admin",
        email="admin@enterticket.com",
        password_hash=pw.hash_password("Admin@12345"),
        role=UserRole.ADMIN,
    )

    agent_a = repo.add_user(
        username="客服小王",
        email="agent_a@enterticket.com",
        password_hash=pw.hash_password("Agent@12345"),
        role=UserRole.AGENT,
    )

    agent_b = repo.add_user(
        username="客服小李",
        email="agent_b@enterticket.com",
        password_hash=pw.hash_password("Agent@12345"),
        role=UserRole.AGENT,
    )

    customer_x = repo.add_user(
        username="张三",
        email="customer_x@enterticket.com",
        password_hash=pw.hash_password("User@12345"),
        role=UserRole.CUSTOMER,
    )

    customer_y = repo.add_user(
        username="李四",
        email="customer_y@enterticket.com",
        password_hash=pw.hash_password("User@12345"),
        role=UserRole.CUSTOMER,
    )

    print(f"Users created: admin, 客服小王, 客服小李, 张三, 李四")

    # ── Categories (all active) ──
    cat_hw = repo.create_category(name="硬件故障", actor_user=admin_user)
    cat_sw = repo.create_category(name="软件问题", actor_user=admin_user)
    cat_net = repo.create_category(name="网络异常", actor_user=admin_user)
    cat_return = repo.create_category(name="退换货申请", actor_user=admin_user)

    # One inactive category for testing
    cat_old = repo.create_category(name="历史分类", actor_user=admin_user)
    repo.update_category_status(
        category_id=cat_old["id"],
        status=CategoryStatus.INACTIVE,
        actor_user=admin_user,
    )

    print(f"Categories created: 硬件故障, 软件问题, 网络异常, 退换货申请, 历史分类(停用)")

    # ── Tickets ──
    t1_bundle = repo.create_customer_ticket(
        category_id=cat_hw["id"],
        title="打印机无法连接",
        description="办公室HP打印机一直显示离线，已重启多次。",
        customer_user=customer_x,
    )

    t2_bundle = repo.create_customer_ticket(
        category_id=cat_sw["id"],
        title="报销系统登录报错",
        description="登录后显示500错误，浏览器Chrome最新版。",
        customer_user=customer_x,
    )

    t3_bundle = repo.create_customer_ticket(
        category_id=cat_net["id"],
        title="公司WiFi频繁断连",
        description="工位WiFi每隔几分钟就断开，其他同事正常。",
        customer_user=customer_y,
    )

    t4_bundle = repo.create_customer_ticket(
        category_id=cat_return["id"],
        title="申请更换损坏的显示器",
        description="收到货发现屏幕有裂痕，申请换货。",
        customer_user=customer_y,
    )

    t5_bundle = repo.create_customer_ticket(
        category_id=cat_sw["id"],
        title="OA系统审批流程卡住",
        description="提交审批后一直显示待审核，已超过3天。",
        customer_user=customer_x,
    )

    t1 = t1_bundle["id"]
    t2 = t2_bundle["id"]
    t3 = t3_bundle["id"]
    t4 = t4_bundle["id"]
    t5 = t5_bundle["id"]

    print(f"Tickets created: t1={t1[:8]}..., t2={t2[:8]}..., t3={t3[:8]}..., t4={t4[:8]}..., t5={t5[:8]}...")

    # ── t1: 打印机 → assign → processing → resolved ──
    repo.assign_internal_ticket(ticket_id=t1, assignee_user_id=agent_a["id"], actor_user=admin_user)
    repo.update_internal_ticket_status(ticket_id=t1, ticket_status=TicketStatus.PROCESSING, actor_user=agent_a)
    repo.add_customer_ticket_message(ticket_id=t1, customer_user=customer_x, content="请问大概什么时候能处理？")
    repo.add_internal_ticket_message(ticket_id=t1, sender_user=agent_a, content="已联系维修人员，预计明天上门。")
    repo.update_internal_ticket_status(ticket_id=t1, ticket_status=TicketStatus.RESOLVED, actor_user=agent_a)

    # ── t2: 报销系统 → assign → processing ──
    repo.assign_internal_ticket(ticket_id=t2, assignee_user_id=agent_b["id"], actor_user=admin_user)
    repo.update_internal_ticket_status(ticket_id=t2, ticket_status=TicketStatus.PROCESSING, actor_user=agent_b)
    repo.add_internal_ticket_message(ticket_id=t2, sender_user=agent_b, content="正在排查500错误原因。")

    # ── t3: WiFi → assign → processing → messages → resolved → closed ──
    repo.assign_internal_ticket(ticket_id=t3, assignee_user_id=agent_a["id"], actor_user=admin_user)
    repo.update_internal_ticket_status(ticket_id=t3, ticket_status=TicketStatus.PROCESSING, actor_user=agent_a)
    repo.add_customer_ticket_message(ticket_id=t3, customer_user=customer_y, content="好的，麻烦尽快。")
    repo.add_internal_ticket_message(ticket_id=t3, sender_user=agent_a, content="已安排网络组排查，初步判断是AP问题。")
    repo.update_internal_ticket_status(ticket_id=t3, ticket_status=TicketStatus.RESOLVED, actor_user=agent_a)
    repo.update_internal_ticket_status(ticket_id=t3, ticket_status=TicketStatus.CLOSED, actor_user=agent_a)

    # ── t4: 显示器 → assign → processing → messages → resolved → closed ──
    repo.assign_internal_ticket(ticket_id=t4, assignee_user_id=agent_b["id"], actor_user=admin_user)
    repo.update_internal_ticket_status(ticket_id=t4, ticket_status=TicketStatus.PROCESSING, actor_user=agent_b)
    repo.add_customer_ticket_message(ticket_id=t4, customer_user=customer_y, content="屏幕裂痕照片已上传（模拟）。")
    repo.add_internal_ticket_message(ticket_id=t4, sender_user=agent_b, content="已核实，确认出厂瑕疵，已提交换货流程。")
    repo.update_internal_ticket_status(ticket_id=t4, ticket_status=TicketStatus.RESOLVED, actor_user=agent_b)
    repo.update_internal_ticket_status(ticket_id=t4, ticket_status=TicketStatus.CLOSED, actor_user=agent_b)

    # ── t5: OA审批 → remains unassigned ──

    print("All assignments, messages, and status transitions done.")

    # ── Summary ──
    print("\n=== 种子数据创建完成 ===")
    print("  admin:     admin@enterticket.com / Admin@12345")
    print("  客服小王:  agent_a@enterticket.com / Agent@12345")
    print("  客服小李:  agent_b@enterticket.com / Agent@12345")
    print("  张三:      customer_x@enterticket.com / User@12345")
    print("  李四:      customer_y@enterticket.com / User@12345")
    print("\n工单状态分布:")
    print("  t1 打印机无法连接  → 已解决 (客服小王)")
    print("  t2 报销系统登录报错 → 处理中 (客服小李)")
    print("  t3 WiFi频繁断连    → 已关闭 (客服小王)")
    print("  t4 显示器损坏       → 已关闭 (客服小李)")
    print("  t5 OA审批流程卡住   → 待分配 (无人)")


if __name__ == "__main__":
    seed()
