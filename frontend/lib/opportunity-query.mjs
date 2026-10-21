export const OPPORTUNITY_STATUSES = ["open", "treated", "rejected"];
export const OPPORTUNITY_PRESENCE_STATUSES = ["active", "missing", "resolved_externally"];
export const OPPORTUNITY_SEVERITIES = ["high", "medium", "low"];
export const OPPORTUNITY_SORTS = [
  "created_at",
  "first_seen_at",
  "last_seen_at",
  "archived_at",
  "severity",
  "estimated_savings",
  "status",
];
export const OPPORTUNITY_ORDERS = ["asc", "desc"];
export const OPPORTUNITY_PAGE_SIZES = [25, 50, 100];
export const OPPORTUNITY_VIEWS = ["operational", "history"];
export const OPPORTUNITY_ARCHIVE_REASONS = ["MANUAL", "RETENTION_POLICY"];
export const OPPORTUNITY_DATE_FIELDS = ["first_seen", "last_seen"];
export const OPPORTUNITY_TIME_PRESETS = ["", "today", "last_24h", "last_7d", "last_30d", "custom"];
export const OPPORTUNITY_DISCOVERY_TYPES = [
  "",
  "observed",
  "first_seen",
  "new_vs_previous",
  "reappeared",
  "continued",
];

function positiveInteger(value, fallback) {
  const parsed = Number.parseInt(value || "", 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function selectedTemporalValue(params, field, suffix) {
  return params.get(`${field}_${suffix}`) || "";
}

function inputDate(value) {
  if (!value) return "";
  return value.includes("T") ? value.slice(0, 10) : value;
}

export function parseOpportunitySearchParams(value) {
  const params = value instanceof URLSearchParams ? value : new URLSearchParams(value || "");
  const view = params.get("view") === "history" ? "history" : "operational";
  const requestedStatus = params.get("status") || (view === "history" ? "" : "open");
  const requestedPresence = params.get("presence_status") || "";
  const requestedSeverity = params.get("severity") || "";
  const requestedSort = params.get("sort") || (view === "history" ? "archived_at" : "last_seen_at");
  const requestedOrder = params.get("order") || "desc";
  const requestedPageSize = positiveInteger(params.get("page_size"), 50);
  const requestedArchiveReason = params.get("archive_reason") || "";
  const requestedDateField = params.get("date_field") || "first_seen";
  const dateField = OPPORTUNITY_DATE_FIELDS.includes(requestedDateField) ? requestedDateField : "first_seen";
  const requestedPreset = params.get("identified_preset") || "";
  const temporalFromRaw = selectedTemporalValue(params, dateField, "from");
  const temporalToRaw = selectedTemporalValue(params, dateField, "to");
  const requestedDiscoveryType = params.get("discovery_type") || "";

  return {
    view,
    status: OPPORTUNITY_STATUSES.includes(requestedStatus) ? requestedStatus : (view === "history" ? "" : "open"),
    presenceStatus: OPPORTUNITY_PRESENCE_STATUSES.includes(requestedPresence) ? requestedPresence : "",
    provider: params.get("provider") || "",
    accountId: params.get("account_id") || "",
    region: params.get("region") || "",
    service: params.get("service") || "",
    resourceType: params.get("resource_type") || "",
    severity: OPPORTUNITY_SEVERITIES.includes(requestedSeverity) ? requestedSeverity : "",
    rule: params.get("rule") || params.get("rule_key") || "",
    collectionRunId: params.get("collection_run_id") || "",
    firstSeenCollectionRunId: params.get("first_seen_collection_run_id") || "",
    discoveryType: OPPORTUNITY_DISCOVERY_TYPES.includes(requestedDiscoveryType) ? requestedDiscoveryType : "",
    resourceId: params.get("resource_id") || "",
    search: params.get("search") || "",
    dateField,
    temporalPreset: requestedPreset && OPPORTUNITY_TIME_PRESETS.includes(requestedPreset)
      ? requestedPreset
      : (temporalFromRaw || temporalToRaw ? "custom" : ""),
    temporalFrom: inputDate(temporalFromRaw),
    temporalTo: inputDate(temporalToRaw),
    temporalFromRaw,
    temporalToRaw,
    archivedFrom: params.get("archived_from") || "",
    archivedTo: params.get("archived_to") || "",
    archiveReason: OPPORTUNITY_ARCHIVE_REASONS.includes(requestedArchiveReason) ? requestedArchiveReason : "",
    page: positiveInteger(params.get("page"), 1),
    pageSize: OPPORTUNITY_PAGE_SIZES.includes(requestedPageSize) ? requestedPageSize : 50,
    sort: OPPORTUNITY_SORTS.includes(requestedSort)
      ? requestedSort
      : (view === "history" ? "archived_at" : "last_seen_at"),
    order: OPPORTUNITY_ORDERS.includes(requestedOrder) ? requestedOrder : "desc",
    opportunityId: params.get("opportunity_id") || "",
    current: view === "operational" && params.get("current") === "true",
  };
}

function addFilter(params, key, value) {
  if (value !== undefined && value !== null && String(value).trim() !== "") {
    params.set(key, String(value).trim());
  }
}

function archivedBoundary(value, endOfDay = false) {
  if (!value) return "";
  if (value.includes("T")) return value;
  return `${value}T${endOfDay ? "23:59:59.999999" : "00:00:00"}Z`;
}

function dateOnlyBoundary(value, endExclusive = false) {
  if (!value) return "";
  if (value.includes("T")) return value;
  const [year, month, day] = value.split("-").map(Number);
  if (![year, month, day].every(Number.isFinite)) return value;
  const local = new Date(year, month - 1, day + (endExclusive ? 1 : 0), 0, 0, 0, 0);
  return local.toISOString();
}

export function resolveOpportunityTemporalWindow(state, anchorValue = new Date()) {
  const field = state.dateField === "last_seen" ? "last_seen" : "first_seen";
  const preset = state.temporalPreset || "";
  const anchor = anchorValue instanceof Date ? new Date(anchorValue.getTime()) : new Date(anchorValue);
  if (Number.isNaN(anchor.getTime())) throw new Error("Invalid temporal anchor");

  if (!preset) return { field, from: "", to: "" };
  if (preset === "custom") {
    const fromSource = state.temporalFromRaw || state.temporalFrom;
    const toSource = state.temporalToRaw || state.temporalTo;
    return {
      field,
      from: dateOnlyBoundary(fromSource),
      to: dateOnlyBoundary(toSource, true),
    };
  }

  if (preset === "today") {
    const from = new Date(anchor.getFullYear(), anchor.getMonth(), anchor.getDate(), 0, 0, 0, 0);
    const to = new Date(from.getFullYear(), from.getMonth(), from.getDate() + 1, 0, 0, 0, 0);
    return { field, from: from.toISOString(), to: to.toISOString() };
  }

  const durations = {
    last_24h: 24 * 60 * 60 * 1000,
    last_7d: 7 * 24 * 60 * 60 * 1000,
    last_30d: 30 * 24 * 60 * 60 * 1000,
  };
  const duration = durations[preset];
  if (!duration) return { field, from: "", to: "" };
  return {
    field,
    from: new Date(anchor.getTime() - duration).toISOString(),
    to: anchor.toISOString(),
  };
}

function addTemporalFilters(params, state, options = {}) {
  const window = resolveOpportunityTemporalWindow(state, options.now || new Date());
  if (!window.from && !window.to) return;
  addFilter(params, `${window.field}_from`, window.from);
  addFilter(params, `${window.field}_to`, window.to);
}

function addSharedFilters(params, state, options = {}) {
  addFilter(params, "provider", state.provider);
  addFilter(params, "account_id", state.accountId);
  addFilter(params, "region", state.region);
  addFilter(params, "service", state.service);
  addFilter(params, "resource_type", state.resourceType);
  addFilter(params, "severity", state.severity);
  addFilter(params, "rule", state.rule);
  addFilter(params, "collection_run_id", state.collectionRunId);
  addFilter(params, "first_seen_collection_run_id", state.firstSeenCollectionRunId);
  addFilter(params, "discovery_type", state.collectionRunId ? state.discoveryType : "");
  addFilter(params, "resource_id", state.resourceId);
  addFilter(params, "search", state.search);
  addTemporalFilters(params, state, options);

  if (state.view === "history") {
    params.set("archive_state", "archived");
    addFilter(params, "presence_status", state.presenceStatus);
    addFilter(params, "archived_from", archivedBoundary(state.archivedFrom));
    addFilter(params, "archived_to", archivedBoundary(state.archivedTo, true));
    addFilter(params, "archive_reason", state.archiveReason);
  } else if (state.current) {
    params.set("current", "true");
  }
}

export function buildOpportunityApiQuery(state, options = {}) {
  const params = new URLSearchParams();
  addFilter(params, "status", state.status);
  params.set("page", String(state.page));
  params.set("page_size", String(state.pageSize));
  params.set("sort", state.sort);
  params.set("order", state.order);
  addSharedFilters(params, state, options);
  return params.toString();
}

export function buildOpportunityStatsQuery(state, options = {}) {
  const params = new URLSearchParams();
  addSharedFilters(params, state, options);
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
