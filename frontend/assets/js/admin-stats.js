import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";
import { sessionReady } from "./session-ui.js";

const rangeBtns = document.querySelectorAll("[data-range-btn]");
let currentRange = "7d";

const statusTexts = {
  unassigned: "待分配",
  processing: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) return "";
  return value.replace("T", " ").replace("Z", "");
}

async function loadStats() {
  showFeedback("正在加载数据...", "");
  try {
    const data = await apiRequest(`/api/v1/admin/stats?range=${currentRange}`);
    renderOverview(data?.overview ?? {});
    renderTrend(data?.trend ?? []);
    renderAvgTimes(data?.avg_times ?? {});
    renderCategoryDist(data?.category_dist ?? []);
    renderAgentWorkload(data?.agent_workload ?? []);
    renderRecentLogs(data?.recent_logs ?? []);
    showFeedback(`数据已加载（${currentRange === "all" ? "全部" : currentRange}）`, "success");
  } catch (error) {
    if (error.status === 401) {
      showFeedback("请先登录管理员账号。", "error");
      return;
    }
    if (error.status === 403) {
      showFeedback("当前账号无权访问该页面。", "error");
      return;
    }
    showErrorFeedback(error);
  }
}

function renderOverview(overview) {
  const el = document.querySelector("[data-overview]");
  if (!el) return;
  if (overview.total === 0) {
    el.innerHTML = '<div class="meta">暂无数据</div>';
    return;
  }
  const bars = Object.entries(overview.by_status)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => {
      const pct = Math.round((count / overview.total) * 100);
      return `<div class="stat-row">
        <span class="stat-label">${escapeHtml(statusTexts[status] || status)}</span>
        <span class="stat-value">${count}</span>
        <div class="stat-bar"><div class="stat-bar-fill" style="width:${pct}%"></div></div>
      </div>`;
    })
    .join("");
  el.innerHTML = `<div class="stat-total">共 ${overview.total} 单</div>${bars}`;
}

function renderTrend(trend) {
  const el = document.querySelector("[data-trend]");
  if (!el) return;
  if (trend.length === 0) {
    el.innerHTML = '<div class="meta">暂无数据</div>';
    return;
  }
  const maxCount = Math.max(...trend.map((d) => d.count));
  const bars = trend
    .map((d) => {
      const height = maxCount > 0 ? Math.max((d.count / maxCount) * 80, 4) : 4;
      const label = d.date.length === 10 ? d.date.slice(5) : d.date.slice(0, 7);
      return `<div class="trend-bar-wrap">
        <div class="trend-bar" style="height:${height}px" title="${d.count} 单"></div>
        <div class="trend-label">${escapeHtml(label)}</div>
      </div>`;
    })
    .join("");
  el.innerHTML = `<div class="trend-chart">${bars}</div>`;
}

function renderAvgTimes(avgTimes) {
  const el = document.querySelector("[data-avg-times]");
  if (!el) return;
  if (avgTimes.overall_avg_hours === 0) {
    el.innerHTML = '<div class="meta">暂无已关闭工单数据</div>';
    return;
  }
  el.innerHTML = `
    <div class="stat-row">
      <span class="stat-label">总平均时长</span>
      <span class="stat-value">${avgTimes.overall_avg_hours}h</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">待分配阶段</span>
      <span class="stat-value">${avgTimes.unassigned_avg_hours}h</span>
    </div>
    <div class="stat-row">
      <span class="stat-label">处理中阶段</span>
      <span class="stat-value">${avgTimes.processing_avg_hours}h</span>
    </div>
  `;
}

function renderCategoryDist(dist) {
  const el = document.querySelector("[data-category-dist]");
  if (!el) return;
  if (dist.length === 0) {
    el.innerHTML = '<div class="meta">暂无数据</div>';
    return;
  }
  const rows = dist
    .map((item) => {
      return `<div class="stat-row">
        <span class="stat-label">${escapeHtml(item.name)}</span>
        <span class="stat-value">${item.count} (${item.percentage}%)</span>
        <div class="stat-bar"><div class="stat-bar-fill" style="width:${item.percentage}%"></div></div>
      </div>`;
    })
    .join("");
  el.innerHTML = rows;
}

function renderAgentWorkload(workload) {
  const el = document.querySelector("[data-agent-workload]");
  if (!el) return;
  if (workload.length === 0) {
    el.innerHTML = '<div class="meta">暂无数据</div>';
    return;
  }
  const rows = workload
    .map(
      (agent) => `
      <tr>
        <td>${escapeHtml(agent.username)}</td>
        <td>${agent.assigned}</td>
        <td>${agent.processing}</td>
        <td>${agent.resolved}</td>
        <td>${agent.closed}</td>
      </tr>`
    )
    .join("");
  el.innerHTML = `<table>
    <thead><tr><th>客服</th><th>分配</th><th>处理中</th><th>已解决</th><th>已关闭</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function renderRecentLogs(logs) {
  const el = document.querySelector("[data-recent-logs]");
  if (!el) return;
  if (logs.length === 0) {
    el.innerHTML = '<div class="meta">暂无动态</div>';
    return;
  }
  const items = logs
    .map((log) => {
      let detail = "";
      if (log.action === "ticket_status_changed") {
        const from = escapeHtml(statusTexts[log.from_status] || log.from_status || "");
        const to = escapeHtml(statusTexts[log.to_status] || log.to_status || "");
        detail = `${from} → ${to}`;
      } else if (log.action === "ticket_assigned" || log.action === "ticket_reassigned") {
        detail = "已分配";
      } else if (log.action === "ticket_created") {
        detail = "新建工单";
      } else {
        detail = escapeHtml(log.action);
      }
      return `<div class="audit-item">
        <strong>${escapeHtml(log.ticket_title)}</strong> — ${detail}
        <div class="meta">${escapeHtml(log.by_username)} · ${formatDate(log.created_at)}</div>
      </div>`;
    })
    .join("");
  el.innerHTML = `<div class="audit-list">${items}</div>`;
}

(async function initDashboard() {
  const user = await sessionReady;
  if (!user || user.role !== "admin") return;

  rangeBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      rangeBtns.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentRange = btn.dataset.rangeBtn;
      loadStats();
    });
  });

  await loadStats();
})();
