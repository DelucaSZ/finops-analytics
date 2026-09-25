export const OPPORTUNITY_STATUSES = ["open", "treated", "rejected"];
export const OPPORTUNITY_SEVERITIES = ["high", "medium", "low"];
export const OPPORTUNITY_SORTS = [
  "created_at",
  "first_seen_at",
  "last_seen_at",
  "severity",
  "estimated_savings",
  "status",
];
export const OPPORTUNITY_ORDERS = ["asc", "desc"];
export const OPPORTUNITY_PAGE_SIZES = [25, 50, 100];

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function parseOpportunitySearchParams(value) {
  const params = value instanceof URLSearchParams ? value : new URLSearchParams(value || "");
  const requestedStatus = params.get("status") || "open";
  const requestedSeverity = params.get("severity") || "";
  const requestedSort = params.get("sort") || "last_seen_at";
  const requestedOrder = params.get("order") || "desc";
  const requestedPageSize = positiveInteger(params.get("page_size"), 50);

  return {
    status: OPPORTUNITY_STATUSES.includes(requestedStatus) ? requestedStatus : "open",
    provider: params.get("provider") || "",
    accountId: params.get("account_id") || "",
    region: params.get("region") || "",
    severity: OPPORTUNITY_SEVERITIES.includes(requestedSeverity) ? requestedSeverity : "",
    rule: params.get("rule") || params.get("rule_key") || "",
    collectionRunId: params.get("collection_run_id") || "",
    resourceId: params.get("resource_id") || "",
    search: params.get("search") || "",
    page: positiveInteger(params.get("page"), 1),
    pageSize: OPPORTUNITY_PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : 50,
    sort: OPPORTUNITY_SORTS.includes(requestedSort) ? requestedSort : "last_seen_at",
    order: OPPORTUNITY_ORDERS.includes(requestedOrder) ? requestedOrder : "desc",
    opportunityId: params.get("opportunity_id") || "",
  };
}

function addFilter(params, key, value) {
  if (value !== undefined && value !== null && String(value).trim() !== "") {
    params.set(key, String(value).trim());
  }
}

export function buildOpportunityApiQuery(state) {
  const params = new URLSearchParams();
  params.set("status", state.status);
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  params.set("sort", state.sort);
  params.set("order", state.order);
  addFilter(params, "provider", state.provider);
  addFilter(params, "account_id", state.accountId);
  addFilter(params, "region", state.region);
  addFilter(params, "severity", state.severity);
  addFilter(params, "rule", state.rule);
  addFilter(params, "collection_run_id", state.collectionRunId);
  addFilter(params, "resource_id", state.resourceId);
  addFilter(params, "search", state.search);
  return params.toString();
}

export function buildOpportunityStatsQuery(state) {
  const params = new URLSearchParams();
  addFilter(params, "provider", state.provider);
  addFilter(params, "account_id", state.accountId);
  addFilter(params, "region", state.region);
  addFilter(params, "severity", state.severity);
  addFilter(params, "rule", state.rule);
  addFilter(params, "collection_run_id", state.collectionRunId);
  addFilter(params, "resource_id", state.resourceId);
  addFilter(params, "search", state.search);
  return params.toString();
}

export function patchOpportunityUrl(current, patch, options = {}) {
  const params = current instanceof URLSearchParams
    ? new URLSearchParams(current.toString())
    : new URLSearchParams(current || "");
  const resetPage = options.resetPage !== false;

  for (const [key, value] of Object.entries(patch)) {
    if (value === undefined || value === null || value === "" || value === "all") {
      params.delete(key);
    } else {
      params.set(key, String(value));
    }
  }

  if (resetPage && !("page" in patch)) params.set("page", "1");
  return params;
}

export function buildLifecycleRequest({ action, opportunityIds, reason, note, bulk }) {
  if (!opportunityIds?.length) throw new Error("At least one opportunity is required");
  if (!["treat", "reject", "reopen"].includes(action)) throw new Error("Unsupported lifecycle action");

  const trimmedNote = typeof note === "string" && note.trim() ? note.trim() : undefined;
  const payload = action === "reject"
    ? { reason, ...(trimmedNote ? { note: trimmedNote } : {}) }
    : (trimmedNote ? { note: trimmedNote } : {});

  if (bulk) {
    payload.opportunity_ids = [...new Set(opportunityIds)];
    return { path: `/opportunities/bulk/${action}`, body: payload };
  }
  if (opportunityIds.length !== 1) throw new Error("Individual lifecycle action requires one opportunity");
  return { path: `/opportunities/${opportunityIds[0]}/${action}`, body: payload };
}

export function rejectionRequiresNote(reason) {
  return reason === "OTHER";
}
