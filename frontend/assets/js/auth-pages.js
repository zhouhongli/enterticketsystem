import { apiRequest } from "./api-client.js";
import { showErrorFeedback, showFeedback } from "./form-utils.js";

const page = document.body.dataset.authPage;

function setBusy(form, busy) {
  form.querySelectorAll("button, input").forEach((control) => {
    control.disabled = busy;
  });
}

function readForm(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function trimValues(data, keys) {
  keys.forEach((key) => {
    data[key] = String(data[key] || "").trim();
  });
  return data;
}

function roleHome(role) {
  if (role === "customer") {
    return "/pages/customer/tickets.html";
  }
  if (role === "agent" || role === "admin") {
    return "/pages/internal/tickets.html";
  }
  return null;
}

function redirectByRole(user) {
  const target = roleHome(user?.role);
  if (!target) {
    showFeedback("当前账号角色无法进入系统。", "error");
    return;
  }
  window.location.href = target;
}

async function redirectExistingSession() {
  try {
    const user = await apiRequest("/api/v1/auth/me");
    redirectByRole(user);
  } catch (_error) {
    // Anonymous users stay on the login page.
  }
}

function initLogin() {
  const form = document.querySelector("[data-login-form]");
  const params = new URLSearchParams(window.location.search);
  if (params.get("registered") === "1") {
    showFeedback("注册成功，请登录。", "success");
  } else if (params.get("logged_out") === "1") {
    showFeedback("已退出登录。", "success");
  } else if (params.get("auth") === "required") {
    showFeedback("请先登录后继续操作。", "error");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = trimValues(readForm(form), ["identifier"]);
    if (!data.identifier || !data.password) {
      showFeedback("填写必填信息。", "error");
      return;
    }

    setBusy(form, true);
    try {
      const user = await apiRequest("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify(data),
      });
      redirectByRole(user);
    } catch (error) {
      showErrorFeedback(error, "登录失败，请检查后重试。");
    } finally {
      setBusy(form, false);
    }
  });

  redirectExistingSession();
}

function clearPasswords(form) {
  form.querySelectorAll('input[type="password"]').forEach((input) => {
    input.value = "";
  });
}

function validateRegister(data) {
  if (!data.username || !data.email || !data.password || !data.confirm_password) {
    return "填写必填信息。";
  }
  if (data.username.length < 3 || data.username.length > 50) {
    return "用户名长度需为 3 至 50 个字符。";
  }
  if (data.email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email)) {
    return "电子邮箱格式不正确。";
  }
  if (data.password.length < 8 || data.password.length > 128) {
    return "密码长度需为 8 至 128 个字符。";
  }
  if (data.password !== data.confirm_password) {
    return "两次输入的密码不一致。";
  }
  return "";
}

function initRegister() {
  const form = document.querySelector("[data-register-form]");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = trimValues(readForm(form), ["username", "email"]);
    const errorMessage = validateRegister(data);
    if (errorMessage) {
      showFeedback(errorMessage, "error");
      clearPasswords(form);
      return;
    }

    setBusy(form, true);
    try {
      await apiRequest("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify(data),
      });
      window.location.href = "/pages/login.html?registered=1";
    } catch (error) {
      showErrorFeedback(error, "注册失败，请检查后重试。");
      clearPasswords(form);
    } finally {
      setBusy(form, false);
    }
  });
}

if (page === "login") {
  initLogin();
} else if (page === "register") {
  initRegister();
}
