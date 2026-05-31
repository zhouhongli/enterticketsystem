from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.models import parse_utc
from app.repositories.json_repository import JsonRepository

RANGE_DAYS = {"7d": 7, "30d": 30, "90d": 90}


class AdminStatsService:
    def __init__(self, repository: JsonRepository) -> None:
        self.repository = repository

    def get_stats(self, range_: str) -> dict[str, Any]:
        cutoff = self._cutoff(range_)
        all_tickets = self.repository.list_internal_tickets()
        all_audit_logs = self.repository.list_audit_logs()
        all_categories = self.repository.list_categories()
        all_users = self.repository.list_users()

        filtered_tickets = [
            t for t in all_tickets
            if cutoff is None or parse_utc(t["ticket"]["created_at"]) >= cutoff
        ]

        return {
            "overview": self._overview(filtered_tickets),
            "trend": self._trend(filtered_tickets, range_),
            "avg_times": self._avg_times(all_audit_logs),
            "category_dist": self._category_dist(filtered_tickets, all_categories),
            "agent_workload": self._agent_workload(filtered_tickets, all_users),
            "recent_logs": self._recent_logs(all_audit_logs, all_users),
        }

    def _cutoff(self, range_: str) -> datetime | None:
        if range_ == "all":
            return None
        days = RANGE_DAYS.get(range_, 7)
        return datetime.now(timezone.utc) - timedelta(days=days)

    def _overview(self, tickets: list[dict]) -> dict[str, Any]:
        by_status = {
            "unassigned": 0,
            "processing": 0,
            "resolved": 0,
            "closed": 0,
        }
        for bundle in tickets:
            status = bundle["ticket"]["status"]
            if status in by_status:
                by_status[status] += 1
        return {"total": len(tickets), "by_status": by_status}

    def _trend(self, tickets: list[dict], range_: str) -> list[dict[str, Any]]:
        date_counts: dict[str, int] = {}
        for bundle in tickets:
            created = bundle["ticket"]["created_at"]
            dt = parse_utc(created)
            if range_ == "all":
                week_start = dt - timedelta(days=dt.weekday())
                key = week_start.strftime("%Y-%m-%d")
            else:
                key = dt.strftime("%Y-%m-%d")
            date_counts[key] = date_counts.get(key, 0) + 1

        sorted_keys = sorted(date_counts.keys())
        return [{"date": k, "count": date_counts[k]} for k in sorted_keys]

    def _avg_times(self, audit_logs: list[dict]) -> dict[str, Any]:
        ticket_logs: dict[str, list[dict]] = {}
        for log in audit_logs:
            tid = log.get("ticket_id")
            if tid:
                ticket_logs.setdefault(tid, []).append(log)

        overall_seconds: list[float] = []
        stage_seconds: dict[str, list[float]] = {
            "unassigned": [],
            "processing": [],
        }

        for tid, logs in ticket_logs.items():
            closed_log = None
            for log in logs:
                if log["action"] == "ticket_status_changed" and log["changes"]["status"]["after"] == "closed":
                    closed_log = log
            if closed_log is None:
                continue

            created_log = None
            for log in logs:
                if log["action"] == "ticket_created":
                    created_log = log
                    break
            if created_log is None:
                continue

            overall = parse_utc(closed_log["occurred_at"]) - parse_utc(created_log["occurred_at"])
            overall_seconds.append(overall.total_seconds())

            status_timeline = []
            for log in sorted(logs, key=lambda x: x["occurred_at"]):
                if log["action"] == "ticket_created":
                    status_timeline.append(("unassigned", log["occurred_at"]))
                elif log["action"] == "ticket_status_changed":
                    after = log["changes"]["status"]["after"]
                    if after in ("processing", "resolved", "closed"):
                        status_timeline.append((after, log["occurred_at"]))

            for i in range(len(status_timeline) - 1):
                stage, start_str = status_timeline[i]
                if stage in stage_seconds:
                    end_str = status_timeline[i + 1][1]
                    delta = parse_utc(end_str) - parse_utc(start_str)
                    stage_seconds[stage].append(delta.total_seconds())

        def avg_hours(seconds_list: list[float]) -> float:
            if not seconds_list:
                return 0
            return round(sum(seconds_list) / len(seconds_list) / 3600, 1)

        return {
            "overall_avg_hours": avg_hours(overall_seconds),
            "unassigned_avg_hours": avg_hours(stage_seconds["unassigned"]),
            "processing_avg_hours": avg_hours(stage_seconds["processing"]),
        }

    def _category_dist(
        self, tickets: list[dict], categories: list[dict]
    ) -> list[dict[str, Any]]:
        cat_name_map = {c["id"]: c["name"] for c in categories}
        cat_counts: dict[str, int] = {}
        for bundle in tickets:
            cat_id = bundle["ticket"]["category_id"]
            cat_counts[cat_id] = cat_counts.get(cat_id, 0) + 1

        total = len(tickets)
        result = []
        for cat_id, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            result.append({
                "name": cat_name_map.get(cat_id, "未知分类"),
                "count": count,
                "percentage": round(count / total * 100, 1) if total > 0 else 0,
            })
        return result

    def _agent_workload(
        self, tickets: list[dict], users: list[dict]
    ) -> list[dict[str, Any]]:
        user_map = {u["id"]: u["username"] for u in users}
        agent_stats: dict[str, dict[str, int]] = {}
        for bundle in tickets:
            assignee_id = bundle["ticket"]["assignee_user_id"]
            if assignee_id is None:
                continue
            if assignee_id not in agent_stats:
                agent_stats[assignee_id] = {
                    "assigned": 0,
                    "processing": 0,
                    "resolved": 0,
                    "closed": 0,
                }
            agent_stats[assignee_id]["assigned"] += 1
            status = bundle["ticket"]["status"]
            if status in agent_stats[assignee_id]:
                agent_stats[assignee_id][status] += 1

        result = []
        for agent_id, stats in sorted(
            agent_stats.items(), key=lambda x: -x[1]["assigned"]
        ):
            result.append({
                "username": user_map.get(agent_id, "未知"),
                **stats,
            })
        return result

    def _recent_logs(
        self, audit_logs: list[dict], users: list[dict]
    ) -> list[dict[str, Any]]:
        user_map = {u["id"]: u["username"] for u in users}
        all_tickets = self.repository.list_internal_tickets()
        ticket_title_map = {
            b["ticket"]["id"]: b["ticket"]["title"] for b in all_tickets
        }

        result = []
        for log in audit_logs[:10]:
            entry = {
                "action": log["action"],
                "ticket_title": ticket_title_map.get(log.get("ticket_id"), "未知工单"),
                "created_at": log["occurred_at"],
                "by_username": user_map.get(log.get("actor_user_id"), "系统"),
            }
            if log["action"] == "ticket_status_changed":
                changes = log.get("changes", {}).get("status", {})
                entry["from_status"] = changes.get("before", "")
                entry["to_status"] = changes.get("after", "")
            elif log["action"] in ("ticket_assigned", "ticket_reassigned"):
                entry["assignee"] = log.get("changes", {}).get("assignee_user_id", {}).get("after", "")
            result.append(entry)
        return result
