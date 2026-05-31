import { formatApiError } from "./api-client.js";

export function showFeedback(message, type = "info") {
  const target = document.querySelector("[data-feedback]");
  if (!target) {
    return;
  }
  target.textContent = message;
  target.dataset.type = type;
}

export function showErrorFeedback(error, fallback = "操作未完成，请稍后重试。") {
  showFeedback(formatApiError(error, fallback), "error");
}
