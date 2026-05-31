import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";

const page = document.body.dataset.adminPage;

function formatDate(value) {
  if (!value) {
    return "";
  }
  return value.replace("T", " ").replace("Z", "");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function statusText(value) {
  return value === "active" ? "启用" : "停用";
}

function userStatusText(value) {
  return value === "active" ? "启用" : "禁用";
}

function setBusy(form, busy) {
  if (!form) {
    return;
  }
  form.querySelectorAll("button, input, select").forEach((control) => {
    control.disabled = busy;
  });
}

function readForm(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function renderEmpty(tbody, colspan, message) {
  tbody.innerHTML = `<tr><td colspan="${colspan}" class="meta">${message}</td></tr>`;
}

function handleError(error) {
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

async function initCategories() {
  const form = document.querySelector("[data-category-form]");
  const tbody = document.querySelector("[data-category-list]");

  async function load() {
    const data = await apiRequest("/api/v1/admin/categories");
    if (data.items.length === 0) {
      renderEmpty(tbody, 4, "暂无分类");
      return;
    }

    tbody.innerHTML = data.items
      .map(
        (category) => `
          <tr data-category-id="${escapeHtml(category.id)}">
            <td><input value="${escapeHtml(category.name)}" maxlength="50" data-category-name></td>
            <td><span class="status">${statusText(category.status)}</span></td>
            <td>${escapeHtml(formatDate(category.created_at))}</td>
            <td class="actions">
              <button type="button" class="secondary" data-save-category>保存</button>
              <button type="button" class="${category.status === "active" ? "danger" : "secondary"}" data-toggle-category>
                ${category.status === "active" ? "停用" : "启用"}
              </button>
            </td>
          </tr>
        `
      )
      .join("");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = readForm(form);
    setBusy(form, true);
    try {
      await apiRequest("/api/v1/admin/categories", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      showFeedback("分类已保存。", "success");
      await load();
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(form, false);
    }
  });

  tbody.addEventListener("click", async (event) => {
    const row = event.target.closest("tr[data-category-id]");
    if (!row) {
      return;
    }
    const id = row.dataset.categoryId;
    try {
      if (event.target.matches("[data-save-category]")) {
        const name = row.querySelector("[data-category-name]").value;
        await apiRequest(`/api/v1/admin/categories/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ name }),
        });
        showFeedback("分类已更新。", "success");
        await load();
      }
      if (event.target.matches("[data-toggle-category]")) {
        const current =
          row.querySelector(".status").textContent === "启用" ? "active" : "inactive";
        const next = current === "active" ? "inactive" : "active";
        if (
          next === "inactive" &&
          !window.confirm("确认停用该分类？历史工单将继续保留原分类显示。")
        ) {
          return;
        }
        await apiRequest(`/api/v1/admin/categories/${id}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: next }),
        });
        showFeedback("分类状态已更新。", "success");
        await load();
      }
    } catch (error) {
      handleError(error);
    }
  });

  await load();
}

async function initAgents() {
  const form = document.querySelector("[data-agent-form]");
  const tbody = document.querySelector("[data-agent-list]");

  async function load() {
    const data = await apiRequest("/api/v1/admin/agents");
    if (data.items.length === 0) {
      renderEmpty(tbody, 3, "暂无客服账号");
      return;
    }
    tbody.innerHTML = data.items
      .map(
        (agent) => `
          <tr>
            <td>${escapeHtml(agent.username)}</td>
            <td>${escapeHtml(agent.email)}</td>
            <td>${escapeHtml(formatDate(agent.created_at))}</td>
          </tr>
        `
      )
      .join("");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = readForm(form);
    setBusy(form, true);
    try {
      await apiRequest("/api/v1/admin/agents", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      form.reset();
      showFeedback("客服账号已创建。", "success");
      await load();
    } catch (error) {
      handleError(error);
    } finally {
      setBusy(form, false);
    }
  });

  await load();
}

async function initCustomers() {
  const tbody = document.querySelector("[data-customer-list]");

  async function load() {
    const data = await apiRequest("/api/v1/admin/customers");
    if (data.items.length === 0) {
      renderEmpty(tbody, 5, "暂无客户账号");
      return;
    }
    tbody.innerHTML = data.items
      .map(
        (customer) => `
          <tr data-customer-id="${escapeHtml(customer.id)}" data-customer-status="${customer.status}">
            <td>${escapeHtml(customer.username)}</td>
            <td>${escapeHtml(customer.email)}</td>
            <td><span class="status">${userStatusText(customer.status)}</span></td>
            <td>${escapeHtml(formatDate(customer.created_at))}</td>
            <td>
              <button type="button" class="${customer.status === "active" ? "danger" : "secondary"}" data-toggle-customer>
                ${customer.status === "active" ? "禁用" : "启用"}
              </button>
            </td>
          </tr>
        `
      )
      .join("");
  }

  tbody.addEventListener("click", async (event) => {
    if (!event.target.matches("[data-toggle-customer]")) {
      return;
    }
    const row = event.target.closest("tr[data-customer-id]");
    const current = row.dataset.customerStatus;
    const next = current === "active" ? "disabled" : "active";
    if (next === "disabled" && !window.confirm("确认禁用该客户？该客户的现有会话将失效。")) {
      return;
    }

    try {
      await apiRequest(
        `/api/v1/admin/customers/${row.dataset.customerId}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: next }),
        }
      );
      showFeedback("客户账号状态已更新。", "success");
      await load();
    } catch (error) {
      handleError(error);
    }
  });

  await load();
}

try {
  if (page === "categories") {
    await initCategories();
  } else if (page === "agents") {
    await initAgents();
  } else if (page === "customers") {
    await initCustomers();
  }
} catch (error) {
  handleError(error);
}
