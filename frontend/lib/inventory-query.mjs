const SORT_FIELDS = new Set([
  "name",
  "provider",
  "account",
  "resource_type",
  "service",
  "region",
  "lifecycle_status",
  "presence_status",
  "first_seen_at",
  "last_seen_at",
]);

const DIRECTIONS = new Set(["asc", "desc"]);
const PRESENCE_STATES = new Set(["active", "missing", "all"]);

export const defaultInventoryQueryState = Object.freeze({
  provider: "",
  account: "",
  region: "",
  resourceType: "",
  lifecycleStatus: "",
  presenceStatus: "active",
  service: "",
  search: "",
  sort: "last_seen_at",
  direction: "desc",
  page: 1,
  pageSize: 50,
});

function text(value) {
  return String(value ?? "").trim();
}

function integer(value, fallback, min, max) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) return fallback;
  return parsed;
}

export function parseInventorySearchParams(params) {
  const sort = text(params.get("sort"));
  const direction = text(params.get("direction"));
  const presenceStatus = text(params.get("presence_status"));

  return {
    provider: text(params.get("provider")),
    account: text(params.get("account_id")),
    region: text(params.get("region")),
    resourceType: text(params.get("resource_type")),
    lifecycleStatus: text(params.get("lifecycle_status")),
    presenceStatus: PRESENCE_STATES.has(presenceStatus) ? presenceStatus : "active",
    service: text(params.get("service")),
    search: text(params.get("search")),
    sort: SORT_FIELDS.has(sort) ? sort : "last_seen_at",
    direction: DIRECTIONS.has(direction) ? direction : "desc",
    page: integer(params.get("page"), 1, 1, Number.MAX_SAFE_INTEGER),
    pageSize: integer(params.get("page_size"), 50, 1, 100),
  };
}

export function buildInventoryApiQuery(state) {
  const params = new URLSearchParams();
  if (state.provider) params.set("provider", state.provider);
  if (state.account) params.set("account_id", state.account);
  if (state.region) params.set("region", state.region);
  if (state.resourceType) params.set("resource_type", state.resourceType);
  if (state.lifecycleStatus) params.set("lifecycle_status", state.lifecycleStatus);
  if (state.presenceStatus && state.presenceStatus !== "all") params.set("presence_status", state.presenceStatus);
  if (state.service) params.set("service", state.service);
  if (state.search) params.set("search", text(state.search));
  params.set("sort", SORT_FIELDS.has(state.sort) ? state.sort : "last_seen_at");
  params.set("direction", DIRECTIONS.has(state.direction) ? state.direction : "desc");
  params.set("page", String(integer(state.page, 1, 1, Number.MAX_SAFE_INTEGER)));
  params.set("page_size", String(integer(state.pageSize, 50, 1, 100)));
  return params.toString();
}

export function buildInventoryOptionsQuery(state) {
  const params = new URLSearchParams();
  if (state.provider) params.set("provider", state.provider);
  if (state.account) params.set("account_id", state.account);
  return params.toString();
}

export function buildInventoryUrlSearch(state) {
  const params = new URLSearchParams();
  if (state.provider) params.set("provider", state.provider);
  if (state.account) params.set("account_id", state.account);
  if (state.region) params.set("region", state.region);
  if (state.resourceType) params.set("resource_type", state.resourceType);
  if (state.lifecycleStatus) params.set("lifecycle_status", state.lifecycleStatus);
  if (state.presenceStatus !== defaultInventoryQueryState.presenceStatus) params.set("presence_status", state.presenceStatus);
  if (state.service) params.set("service", state.service);
  if (state.search) params.set("search", text(state.search));
  if (state.sort !== defaultInventoryQueryState.sort) params.set("sort", state.sort);
  if (state.direction !== defaultInventoryQueryState.direction) params.set("direction", state.direction);
  if (state.page !== defaultInventoryQueryState.page) params.set("page", String(state.page));
  if (state.pageSize !== defaultInventoryQueryState.pageSize) params.set("page_size", String(state.pageSize));
  return params.toString();
}

export function patchInventoryUrl(state, changes) {
  const next = { ...state, ...changes };
  const query = buildInventoryUrlSearch(next);
  return query ? `?${query}` : "";
}
