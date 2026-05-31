import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";
import { sessionReady } from "./session-ui.js";
import { statusLabel } from "./ticket-ui.js";

const senderRoleLabels = {
  customer: "客户",
  agent: "客服",
  admin: "管理员",
};

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

function detailUrl(ticketId) {
  const params = new URLSearchParams({ id: ticketId });
  return `/pages/customer/ticket-detail.html?${params.toString()}`;
}

async function initTicketList() {
  const tbody = query("[data-ticket-list]");
  const empty = query("[data-ticket-empty]");
  if (!tbody) {
    return;
  }

  try {
    const data = await apiRequest("/api/v1/customer/tickets");
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

      appendCell(row, ticket.category_name);

      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = "status";
      status.textContent = statusLabel(ticket.status);
      statusCell.append(status);
      row.append(statusCell);

      appendCell(row, formatDateTime(ticket.created_at));

      const actionCell = document.createElement("td");
      const detailLink = document.createElement("a");
      detailLink.href = detailUrl(ticket.id);
      detailLink.textContent = "查看详情";
      actionCell.append(detailLink);
      row.append(actionCell);

      tbody.append(row);
    });

    setHidden(empty, tickets.length > 0);
    showFeedback(
      tickets.length > 0
        ? "这里只展示当前客户本人创建的工单。"
        : "暂无工单，可创建第一张售后工单。",
      "info"
    );
  } catch (error) {
    tbody.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "secondary";
    retry.textContent = "重新加载";
    retry.addEventListener("click", initTicketList);
    cell.textContent = "工单加载失败。";
    cell.append(document.createTextNode(" "), retry);
    row.append(cell);
    tbody.append(row);
    setHidden(empty, true);
    showErrorFeedback(error, "工单加载失败，请稍后重试。");
  }
}

function validateTicketForm(form) {
  const formData = new FormData(form);
  const categoryId = String(formData.get("category_id") || "").trim();
  const title = String(formData.get("title") || "").trim();
  const description = String(formData.get("description") || "").trim();

  if (!categoryId) {
    return { error: "请选择问题分类。" };
  }
  if (!title || title.length > 100) {
    return { error: "标题需为 1 至 100 个字符。" };
  }
  if (!description || description.length > 4000) {
    return { error: "问题描述需为 1 至 4000 个字符。" };
  }
  return { payload: { category_id: categoryId, title, description } };
}

async function initTicketCreate() {
  const form = query("[data-ticket-create-form]");
  const select = query("[data-category-select]");
  const empty = query("[data-category-empty]");
  if (!form || !select) {
    return;
  }

  const submit = form.querySelector("button[type='submit']");

  try {
    const data = await apiRequest("/api/v1/categories/active");
    const categories = data?.items || [];
    select.replaceChildren();

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "请选择分类";
    select.append(placeholder);

    categories.forEach((category) => {
      const option = document.createElement("option");
      option.value = category.id;
      option.textContent = category.name;
      select.append(option);
    });

    const disabled = categories.length === 0;
    select.disabled = disabled;
    if (submit) {
      submit.disabled = disabled;
    }
    setHidden(empty, !disabled);
    showFeedback(
      disabled ? "暂无可用分类，暂不能创建工单。" : "请选择有效分类，并填写标题和问题描述。",
      disabled ? "error" : "info"
    );
  } catch (error) {
    select.disabled = true;
    if (submit) {
      submit.disabled = true;
    }
    setHidden(empty, true);
    showErrorFeedback(error, "分类加载失败，请稍后重试。");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const { payload, error } = validateTicketForm(form);
    if (error) {
      showFeedback(error, "error");
      return;
    }

    if (submit) {
      submit.disabled = true;
    }
    try {
      const ticket = await apiRequest("/api/v1/customer/tickets", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const params = new URLSearchParams({ id: ticket.id, created: "1" });
      window.location.href = `/pages/customer/ticket-detail.html?${params.toString()}`;
    } catch (requestError) {
      showErrorFeedback(requestError, "工单创建失败，请检查后重试。");
      if (submit) {
        submit.disabled = false;
      }
    }
  });
}

function currentTicketId() {
  return new URLSearchParams(window.location.search).get("id");
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
    const role = senderRoleLabels[message.sender_role] || message.sender_role;
    meta.textContent = `${message.sender_name}（${role}） ${formatDateTime(message.sent_at)}`;

    const content = document.createElement("p");
    content.textContent = message.content;

    article.append(meta, content);
    list.append(article);
  });
}

function renderTicketDetail(ticket) {
  setTicketContentHidden(false);
  setText("[data-ticket-title]", ticket.title);
  setText("[data-ticket-category]", ticket.category_name);
  setText("[data-ticket-status]", statusLabel(ticket.status));
  setText("[data-ticket-created]", formatDateTime(ticket.created_at));
  setText("[data-ticket-updated]", formatDateTime(ticket.updated_at));
  setText("[data-ticket-description]", ticket.description);
  renderMessages(ticket.messages || []);

  const isClosed = ticket.status === "closed";
  setHidden(query("[data-message-form-panel]"), isClosed);
  setHidden(query("[data-closed-notice]"), !isClosed);
}

async function loadTicketDetail(successMessage) {
  const ticketId = currentTicketId();
  if (!ticketId) {
    showFeedback("缺少工单编号，无法加载详情。", "error");
    setTicketContentHidden(true);
    setHidden(query("[data-message-form-panel]"), true);
    return null;
  }

  try {
    const ticket = await apiRequest(`/api/v1/customer/tickets/${encodeURIComponent(ticketId)}`);
    renderTicketDetail(ticket);
    const params = new URLSearchParams(window.location.search);
    if (successMessage) {
      showFeedback(successMessage, "info");
    } else if (params.get("created") === "1") {
      showFeedback("工单创建成功，当前状态为待分配。", "info");
    } else {
      showFeedback(`当前状态：${statusLabel(ticket.status)}。`, "info");
    }
    return ticket;
  } catch (error) {
    if (error.status === 404) {
      showFeedback("工单不存在或无权访问。", "error");
    } else {
      showErrorFeedback(error, "工单详情加载失败，请稍后重试。");
    }
    setTicketContentHidden(true);
    setHidden(query("[data-message-form-panel]"), true);
    setHidden(query("[data-closed-notice]"), true);
    renderMessages([]);
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

async function initTicketDetail() {
  const ticket = await loadTicketDetail();
  const form = query("[data-message-form]");
  if (!form || !ticket) {
    return;
  }

  const submit = form.querySelector("button[type='submit']");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const textarea = form.elements.content;
    const { content, error } = validateMessage(String(textarea.value || ""));
    if (error) {
      showFeedback(error, "error");
      return;
    }

    if (submit) {
      submit.disabled = true;
    }
    try {
      await apiRequest(
        `/api/v1/customer/tickets/${encodeURIComponent(currentTicketId())}/messages`,
        {
          method: "POST",
          body: JSON.stringify({ content }),
        }
      );
      textarea.value = "";
      await loadTicketDetail("留言发送成功。");
    } catch (requestError) {
      showErrorFeedback(requestError, "留言发送失败，请稍后重试。");
      if (requestError.status === 409) {
        await loadTicketDetail();
      }
    } finally {
      if (submit) {
        submit.disabled = false;
      }
    }
  });
}

const page = document.body.dataset.customerPage;

async function initCustomerPage() {
  const user = await sessionReady;
  if (!user || user.role !== "customer") {
    return;
  }

  if (page === "tickets") {
    initTicketList();
  } else if (page === "ticket-new") {
    initTicketCreate();
  } else if (page === "ticket-detail") {
    initTicketDetail();
  }
}

initCustomerPage();
