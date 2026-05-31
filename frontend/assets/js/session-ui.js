import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";

const roleNames = {
  customer: "客户",
  agent: "客服",
  admin: "管理员",
};

const roleLinks = {
  customer: [
    { href: "/pages/customer/tickets.html", label: "我的工单" },
    { href: "/pages/customer/ticket-new.html", label: "新建工单" },
  ],
  agent: [{ href: "/pages/internal/tickets.html", label: "工单列表" }],
  admin: [
    { href: "/pages/internal/dashboard.html", label: "数据看板" },
    { href: "/pages/internal/tickets.html", label: "工单列表" },
    { href: "/pages/internal/categories.html", label: "分类管理" },
    { href: "/pages/internal/agents.html", label: "客服账号" },
    { href: "/pages/internal/customers.html", label: "客户账号" },
  ],
};

function loginUrl(reason = "required") {
  const params = new URLSearchParams({ auth: reason });
  return `/pages/login.html?${params.toString()}`;
}

function roleHome(role) {
  return role === "customer"
    ? "/pages/customer/tickets.html"
    : "/pages/internal/tickets.html";
}

function pageArea() {
  const path = window.location.pathname;
  if (path.startsWith("/pages/customer/")) {
    return "customer";
  }
  if (path.startsWith("/pages/internal/")) {
    return "internal";
  }
  return "unknown";
}

function isAllowedOnCurrentPage(user) {
  const area = pageArea();
  if (area === "customer") {
    return user.role === "customer";
  }
  if (area === "internal") {
    return user.role === "agent" || user.role === "admin";
  }
  return true;
}

function renderIdentity(user) {
  const target = document.querySelector("[data-identity]");
  if (!target) {
    return;
  }
  target.innerHTML = "";
  const text = document.createElement("span");
  text.textContent = `${user.username}｜${roleNames[user.role] || user.role}`;
  const logout = document.createElement("button");
  logout.type = "button";
  logout.className = "link-button";
  logout.textContent = "退出";
  logout.addEventListener("click", async () => {
    logout.disabled = true;
    try {
      await apiRequest("/api/v1/auth/logout", { method: "POST" });
    } catch (_error) {
      // Even if the server already invalidated the session, leave the page.
    }
    window.location.href = "/pages/login.html?logged_out=1";
  });
  target.append(text, document.createTextNode("｜"), logout);
}

function renderNav(user) {
  const nav = document.querySelector(".nav");
  if (!nav) {
    return;
  }
  const links = roleLinks[user.role] || [];
  const currentPath = window.location.pathname;
  nav.innerHTML = "";
  links.forEach((link) => {
    const anchor = document.createElement("a");
    anchor.href = link.href;
    anchor.textContent = link.label;
    if (currentPath === link.href) {
      anchor.setAttribute("aria-current", "page");
    }
    nav.append(anchor);
  });
}

async function initSessionUi() {
  try {
    const user = await apiRequest("/api/v1/auth/me");
    if (!isAllowedOnCurrentPage(user)) {
      window.location.href = roleHome(user.role);
      return null;
    }
    renderIdentity(user);
    renderNav(user);
    return user;
  } catch (error) {
    if (error.status === 401) {
      window.location.href = loginUrl("required");
      return null;
    }
    showErrorFeedback(error, "登录状态校验失败，请重新登录。");
    return null;
  }
}

export const sessionReady = initSessionUi();
