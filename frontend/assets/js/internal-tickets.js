import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";
import { sessionReady } from "./session-ui.js";
import { statusLabel } from "./ticket-ui.js";

const roleLabels = {
  customer: "客户",
  agent: "客服",
  admin: "管理员",
};

const statusActions = {
  unassigned: { status: "processing", label: "开始处理" },
  processing: { status: "resolved", label: "标记已解决" },
  resolved: { status: "closed", label: "关闭工单", danger: true },
};

const auditActionLabels = {
  ticket_created: "创建工单",
  ticket_assigned: "分配工单",
  ticket_reassigned: "重新分配工单",
  ticket_status_changed: "状态变更",
};

let currentUser = null;
let currentTicket = null;

function query(selector) {
  return document.querySelector(selector);
}

function setText(selector, value) {
  const element = query(selector);
  if (element) {
    element.textContent = value || "";
  }
}

function setHidden(element, hidden) {
  if (element) {
    element.hidden = hidden;
  }
}

function setTicketContentHidden(hidden) {
  document.querySelectorAll("[data-ticket-content]").forEach((element) => {
    element.hidden = hidden;
  });
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = value || "-";
  row.append(cell);
  return cell;
}

function renderTableMessage(tbody, colspan, message) {
  tbody.replaceChildren();
  const row = document.createElement("tr");
  const cell = document.createElement("td");
  cell.colSpan = colspan;
  cell.className = "meta";
  cell.textContent = message;
  row.append(cell);
  tbody.append(row);
}

function detailUrl(ticketId) {
  const params = new URLSearchParams({ id: ticketId });
  return `/pages/internal/ticket-detail.html?${params.toString()}`;
}

function currentTicketId() {
  return new URLSearchParams(window.location.search).get("id");
}

function currentStatusFilter() {
  const value = new URLSearchParams(window.location.search).get("status");
  return Object.hasOwn(statusActions, value || "") || value === "closed" ? value : "";
}

function internalCanHandle(ticket) {
  if (!currentUser || !ticket || ticket.status === "closed") {
    return false;
  }
  if (currentUser.role === "admin") {
    return true;
  }
  return currentUser.role === "agent" && ticket.assignee?.id === currentUser.id;
}

function renderFilters(activeStatus) {
  document.querySelectorAll("[data-status-filter]").forEach((filter) => {
    filter.classList.toggle("active", filter.dataset.statusFilter === activeStatus);
  });
}

async function initTicketList() {
  const tbody = query("[data-ticket-list]");
  const empty = query("[data-ticket-empty]");
  if (!tbody) {
    return;
  }

  const status = currentStatusFilter();
  renderFilters(status);
  const path = status
    ? `/api/v1/internal/tickets?status=${encodeURIComponent(status)}`
    : "/api/v1/internal/tickets";

  try {
    const data = await apiRequest(path);
    const tickets = data?.items || [];
    tbody.replaceChildren();

    tickets.forEach((ticket) => {
      const row = document.createElement("tr");

      const titleCell = document.createElement("td");
      const titleLink = document.createElement("a");
      titleLink.href = detailUrl(ticket.id);
      titleLink.textContent = ticket.title;
      titleCell.append(titleLink);
      row.append(titleCell);

      appendCell(row, ticket.customer?.username || "-");
      appendCell(row, ticket.category_name);

      const statusCell = document.createElement("td");
      const statusText = document.createElement("span");
      statusText.className = "status";
      statusText.textContent = statusLabel(ticket.status);
      statusCell.append(statusText);
      row.append(statusCell);

      appendCell(row, ticket.assignee?.username || "未分配");
      appendCell(row, formatDateTime(ticket.created_at));

      const actionCell = document.createElement("td");
      const detailLink = document.createElement("a");
      detailLink.href = detailUrl(ticket.id);
      detailLink.textContent = "查看详情";
      actionCell.append(detailLink);
      row.append(actionCell);

      tbody.append(row);
    });

    if (tickets.length === 0) {
      renderTableMessage(tbody, 7, "当前没有符合状态条件的工单。");
    }
    setHidden(empty, tickets.length > 0);
    showFeedback(
      status
        ? `当前筛选：${statusLabel(status)}。`
        : "内部工单列表默认展示全部状态。",
      "info"
    );
  } catch (error) {
    renderTableMessage(tbody, 7, "内部工单加载失败。");
    setHidden(empty, true);
    showErrorFeedback(error, "内部工单加载失败，请稍后重试。");
  }
}

function renderMessages(messages) {
  const list = query("[data-message-list]");
  if (!list) {
    return;
  }
  list.replaceChildren();
  if (!messages || messages.length === 0) {
    const empty = document.createElement("div");
    empty.className = "meta";
    empty.textContent = "暂无公开留言。";
    list.append(empty);
    return;
  }

  messages.forEach((message) => {
    const article = document.createElement("article");
    article.className = "message";

    const meta = document.createElement("div");
    meta.className = "meta";
    const role = roleLabels[message.sender_role] || message.sender_role;
    meta.textContent = `${message.sender_name}（${role}） ${formatDateTime(message.sent_at)}`;

    const content = document.createElement("p");
    content.textContent = message.content;

    article.append(meta, content);
    list.append(article);
  });
}

function describeAuditChanges(auditLog) {
  const changes = auditLog.changes || {};
  if (changes.status) {
    return `${statusLabel(changes.status.before) || "无"} -> ${statusLabel(changes.status.after)}`;
  }
  if (changes.assignee_user_id) {
    return `${changes.assignee_user_id.before || "未分配"} -> ${changes.assignee_user_id.after || "未分配"}`;
  }
  return "已记录变更。";
}

function renderAuditLogs(auditLogs) {
  const list = query("[data-audit-list]");
  if (!list) {
    return;
  }
  list.replaceChildren();
  if (!auditLogs || auditLogs.length === 0) {
    const empty = document.createElement("div");
    empty.className = "meta";
    empty.textContent = "暂无操作记录。";
    list.append(empty);
    return;
  }

  auditLogs.forEach((auditLog) => {
    const article = document.createElement("article");
    article.className = "audit-item";

    const meta = document.createElement("div");
    meta.className = "meta";
    const role = roleLabels[auditLog.actor?.role] || auditLog.actor?.role || "";
    meta.textContent = `${formatDateTime(auditLog.occurred_at)} ${auditLog.actor?.username || "-"}（${role}）`;

    const content = document.createElement("p");
    const action = auditActionLabels[auditLog.action] || auditLog.action;
    content.textContent = `${action}：${describeAuditChanges(auditLog)}`;

    article.append(meta, content);
    list.append(article);
  });
}

async function loadAgents(ticket) {
  const select = query("[data-assignee-select]");
  const submit = query("[data-assignment-submit]");
  const note = query("[data-assignment-note]");
  if (!select) {
    return;
  }

  select.replaceChildren();
  try {
    const data = await apiRequest("/api/v1/admin/agents");
    const agents = data?.items || [];
    agents.forEach((agent) => {
      const option = document.createElement("option");
      option.value = agent.id;
      option.textContent = agent.username;
      option.selected = ticket.assignee?.id === agent.id;
      select.append(option);
    });

    const disabled = agents.length === 0;
    select.disabled = disabled;
    if (submit) {
      submit.disabled = disabled;
      submit.textContent = ticket.assignee ? "重新分配" : "分配";
    }
    if (note) {
      note.textContent = disabled ? "暂无可分配客服账号。" : "";
    }
  } catch (error) {
    select.disabled = true;
    if (submit) {
      submit.disabled = true;
    }
    if (note) {
      note.textContent = error.message || "客服账号加载失败。";
    }
  }
}

function renderAssignment(ticket) {
  const panel = query("[data-assignment-panel]");
  const canAssign = currentUser?.role === "admin" && ticket.status !== "closed";
  setHidden(panel, !canAssign);
  if (canAssign) {
    loadAgents(ticket);
  }
}

function renderStatusAction(ticket) {
  const panel = query("[data-status-panel]");
  const button = query("[data-status-action]");
  const note = query("[data-status-note]");
  const canHandle = internalCanHandle(ticket);
  const action = statusActions[ticket.status];

  setHidden(panel, !canHandle || !action);
  setText("[data-current-status]", statusLabel(ticket.status));

  if (!button || !action) {
    return;
  }
  button.textContent = action.label;
  button.dataset.nextStatus = action.status;
  button.classList.toggle("danger", Boolean(action.danger));
  if (note) {
    note.textContent = "";
  }
}

function renderMessageForm(ticket) {
  setHidden(query("[data-message-form-panel]"), !internalCanHandle(ticket));
}

function renderNotices(ticket) {
  const closed = ticket.status === "closed";
  const hasAction = internalCanHandle(ticket) || (currentUser?.role === "admin" && !closed);
  setHidden(query("[data-closed-notice]"), !closed);
  setHidden(query("[data-no-action-notice]"), closed || hasAction);
}

function renderTicketDetail(ticket) {
  currentTicket = ticket;
  setTicketContentHidden(false);
  setText("[data-ticket-title]", ticket.title);
  setText("[data-ticket-customer]", ticket.customer?.username || "-");
  setText("[data-ticket-category]", ticket.category_name);
  setText("[data-ticket-status]", statusLabel(ticket.status));
  setText("[data-ticket-assignee]", ticket.assignee?.username || "未分配");
  setText("[data-ticket-created]", formatDateTime(ticket.created_at));
  setText("[data-ticket-updated]", formatDateTime(ticket.updated_at));
  setText("[data-ticket-description]", ticket.description);

  renderAssignment(ticket);
  renderStatusAction(ticket);
  renderMessageForm(ticket);
  renderNotices(ticket);
  renderMessages(ticket.messages || []);
  renderAuditLogs(ticket.audit_logs || []);
}

async function loadTicketDetail(successMessage) {
  const ticketId = currentTicketId();
  if (!ticketId) {
    showFeedback("缺少工单编号，无法加载详情。", "error");
    setTicketContentHidden(true);
    setHidden(query("[data-assignment-panel]"), true);
    setHidden(query("[data-status-panel]"), true);
    setHidden(query("[data-message-form-panel]"), true);
    return null;
  }

  try {
    const ticket = await apiRequest(`/api/v1/internal/tickets/${encodeURIComponent(ticketId)}`);
    renderTicketDetail(ticket);
    showFeedback(successMessage || `当前状态：${statusLabel(ticket.status)}。`, "info");
    return ticket;
  } catch (error) {
    if (error.status === 404) {
      showFeedback("工单不存在。", "error");
    } else {
      showErrorFeedback(error, "工单详情加载失败，请稍后重试。");
    }
    setTicketContentHidden(true);
    setHidden(query("[data-assignment-panel]"), true);
    setHidden(query("[data-status-panel]"), true);
    setHidden(query("[data-message-form-panel]"), true);
    setHidden(query("[data-no-action-notice]"), true);
    setHidden(query("[data-closed-notice]"), true);
    renderMessages([]);
    renderAuditLogs([]);
    return null;
  }
}

function validateMessage(content) {
  const trimmed = content.trim();
  if (!trimmed || trimmed.length > 2000) {
    return { error: "留言内容需为 1 至 2000 个字符。" };
  }
  return { content: trimmed };
}

function setupAssignmentForm() {
  const form = query("[data-assignment-form]");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit']");
    const assigneeUserId = String(new FormData(form).get("assignee_user_id") || "").trim();
    if (!assigneeUserId) {
      showFeedback("请选择负责人。", "error");
      return;
    }

    if (submit) {
      submit.disabled = true;
    }
    try {
      await apiRequest(`/api/v1/internal/tickets/${encodeURIComponent(currentTicketId())}/assignment`, {
        method: "PATCH",
        body: JSON.stringify({ assignee_user_id: assigneeUserId }),
      });
      await loadTicketDetail("负责人已更新。");
    } catch (error) {
      showErrorFeedback(error, "分配失败，请稍后重试。");
      if (error.status === 409 || error.status === 404) {
        await loadTicketDetail();
      }
    } finally {
      if (submit) {
        submit.disabled = false;
      }
    }
  });
}

function setupStatusAction() {
  const button = query("[data-status-action]");
  if (!button) {
    return;
  }
  button.addEventListener("click", async () => {
    const nextStatus = button.dataset.nextStatus;
    if (!nextStatus) {
      return;
    }
    if (
      nextStatus === "closed" &&
      !window.confirm("关闭后不能继续留言、分配或变更状态，确认关闭此工单吗？")
    ) {
      return;
    }

    button.disabled = true;
    try {
      await apiRequest(`/api/v1/internal/tickets/${encodeURIComponent(currentTicketId())}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: nextStatus }),
      });
      await loadTicketDetail("工单状态已更新。");
    } catch (error) {
      showErrorFeedback(error, "状态更新失败，请稍后重试。");
      if (error.status === 409 || error.status === 403 || error.status === 404) {
        await loadTicketDetail();
      }
    } finally {
      button.disabled = false;
    }
  });
}

function setupMessageForm() {
  const form = query("[data-message-form]");
  if (!form) {
    return;
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const textarea = form.elements.content;
    const submit = form.querySelector("button[type='submit']");
    const { content, error } = validateMessage(String(textarea.value || ""));
    if (error) {
      showFeedback(error, "error");
      return;
    }

    if (submit) {
      submit.disabled = true;
    }
    try {
      await apiRequest(`/api/v1/internal/tickets/${encodeURIComponent(currentTicketId())}/messages`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      textarea.value = "";
      await loadTicketDetail("留言已发送。");
    } catch (requestError) {
      showErrorFeedback(requestError, "留言发送失败，请稍后重试。");
      if (requestError.status === 409 || requestError.status === 403 || requestError.status === 404) {
        await loadTicketDetail();
      }
    } finally {
      if (submit) {
        submit.disabled = false;
      }
    }
  });
}

async function initTicketDetail() {
  const ticket = await loadTicketDetail();
  if (!ticket) {
    return;
  }
  setupAssignmentForm();
  setupStatusAction();
  setupMessageForm();
}

const page = document.body.dataset.internalPage;

async function initInternalPage() {
  const user = await sessionReady;
  if (!user || !["agent", "admin"].includes(user.role)) {
    return;
  }
  currentUser = user;

  if (page === "tickets") {
    initTicketList();
  } else if (page === "ticket-detail") {
    initTicketDetail();
  }
}

initInternalPage();
