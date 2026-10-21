export function buildHistorySnapshotQuery({
  cycleId,
  page = 1,
  pageSize = 50,
  sort = "estimated_savings",
  order = "desc",
  provider = "",
  status = "",
  severity = "",
  search = "",
} = {}) {
  if (!cycleId) return "";
  const params = new URLSearchParams({
    cycle_id: cycleId,
    page: String(page),
    page_size: String(pageSize),
    sort,
    order,
  });
  if (provider) params.set("provider", provider);
  if (status) params.set("status", status);
  if (severity) params.set("severity", severity);
  if (search.trim()) params.set("search", search.trim());
  return params.toString();
}

export function chooseHistoryCycle(cycles, requestedId = "") {
  if (!Array.isArray(cycles) || cycles.length === 0) return null;
  const requested = cycles.find((cycle) => cycle.id === requestedId);
  if (requested) return requested;
  return cycles.find((cycle) => cycle.status === "CLOSED") || cycles[0];
}

export function cycleStateLabel(status) {
  return status === "CLOSED" ? "Ciclo fechado" : "Em andamento";
}

export function historyMoneyRows(totals, key) {
  const rows = totals?.[key];
  return Array.isArray(rows)
    ? rows.filter((row) => row && typeof row.currency === "string" && row.amount != null)
    : [];
}
