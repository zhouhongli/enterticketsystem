export const ticketStatusLabels = {
  unassigned: "待分配",
  processing: "处理中",
  resolved: "已解决",
  closed: "已关闭",
};

export function statusLabel(status) {
  return ticketStatusLabels[status] || status;
}
