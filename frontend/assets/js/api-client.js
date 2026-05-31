const fieldNames = {
  assignee_user_id: "负责人",
  category_id: "问题分类",
  confirm_password: "确认密码",
  content: "留言内容",
  description: "问题描述",
  email: "电子邮箱",
  identifier: "用户名或电子邮箱",
  name: "名称",
  password: "密码",
  status: "状态",
  title: "标题",
  username: "用户名",
};

const codeMessages = {
  AUTHENTICATION_REQUIRED: "请先登录后继续操作。",
  CONFLICT: "当前数据状态不允许该操作，请刷新后重试。",
  FORBIDDEN: "当前账号无权执行该操作。",
  LOGIN_FAILED: "账号或密码错误，或账号不可用。",
  RESOURCE_NOT_FOUND: "请求的记录不存在或不可访问。",
  STORAGE_ERROR: "数据保存失败，请稍后重试。",
  VALIDATION_ERROR: "填写的信息不符合要求。",
};

function fieldLabel(field) {
  return fieldNames[field] || field || "请求内容";
}

function fieldErrorSummary(fieldErrors = {}) {
  const fields = Object.keys(fieldErrors);
  if (fields.length === 0) {
    return "";
  }
  return fields.map((field) => fieldLabel(field)).join("、");
}

function buildApiError(status, body) {
  const apiError = body?.error || {};
  const code = apiError.code || "REQUEST_FAILED";
  const fallback = codeMessages[code] || apiError.message || "操作未完成，请稍后重试。";
  const fields = fieldErrorSummary(apiError.field_errors || {});
  const message = code === "VALIDATION_ERROR" && fields
    ? `${fallback} 请检查：${fields}。`
    : apiError.message || fallback;
  const error = new Error(message);
  error.status = status;
  error.code = code;
  error.fieldErrors = apiError.field_errors || {};
  return error;
}

export function formatApiError(error, fallback = "操作未完成，请稍后重试。") {
  if (!error) {
    return fallback;
  }
  if (error.code === "VALIDATION_ERROR") {
    const fields = fieldErrorSummary(error.fieldErrors || {});
    return fields ? `填写的信息不符合要求，请检查：${fields}。` : error.message || fallback;
  }
  if (error.code && codeMessages[error.code]) {
    return error.message || codeMessages[error.code];
  }
  return error.message || fallback;
}

export async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
      ...options,
    });
  } catch (_error) {
    const error = new Error("网络连接失败，请检查本地服务是否正在运行。");
    error.status = 0;
    error.code = "NETWORK_ERROR";
    error.fieldErrors = {};
    throw error;
  }

  const contentType = response.headers.get("content-type") || "";
  let body = null;
  if (contentType.includes("application/json")) {
    try {
      body = await response.json();
    } catch (_error) {
      body = null;
    }
  }

  if (!response.ok) {
    throw buildApiError(response.status, body);
  }

  return body;
}
