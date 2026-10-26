export const RDS_RESERVATION_TABS = ["coverage", "reservations", "expiring", "opportunities"];
export const RDS_COVERAGE_STATUSES = ["FULL", "PARTIAL", "UNCOVERED", "UNKNOWN"];
export const RDS_EXPIRATION_RANGES = ["LE_7", "LE_15", "LE_30", "GT_30", "EXPIRED"];
export const RDS_OPPORTUNITY_TYPES = [
  "RDS_RESERVATION_UNCOVERED",
  "RDS_RESERVATION_PARTIAL_COVERAGE",
  "RDS_RESERVATION_UNUSED_CAPACITY",
  "RDS_RESERVATION_EXPIRING",
];

function one(params, key) {
  return String(params.get(key) || "").trim();
}

function positiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value || ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export function parseRdsReservationSearchParams(input) {
  const params = input instanceof URLSearchParams ? input : new URLSearchParams(input || "");
  const tab = one(params, "tab");
  const coverageStatus = one(params, "coverage").toUpperCase();
  const expirationRange = one(params, "expiration").toUpperCase();
  const opportunityType = one(params, "opportunity_type").toUpperCase();
  return {
    tab: RDS_RESERVATION_TABS.includes(tab) ? tab : "coverage",
    account: one(params, "account"),
    region: one(params, "region"),
    engine: one(params, "engine"),
    family: one(params, "family"),
    instanceClass: one(params, "instance_class"),
    coverageStatus: RDS_COVERAGE_STATUSES.includes(coverageStatus) ? coverageStatus : "",
    reservationStatus: one(params, "reservation_status"),
    expirationRange: RDS_EXPIRATION_RANGES.includes(expirationRange) ? expirationRange : "",
    opportunityType: RDS_OPPORTUNITY_TYPES.includes(opportunityType) ? opportunityType : "",
    opportunityStatus: one(params, "opportunity_status"),
    severity: one(params, "severity"),
    page: positiveInt(params.get("page"), 1),
    pageSize: Math.min(200, positiveInt(params.get("page_size"), 50)),
    sort: one(params, "sort"),
    order: one(params, "order") === "desc" ? "desc" : "asc",
  };
}

export function patchRdsReservationUrl(state, changes) {
  const next = { ...state, ...changes };
  const params = new URLSearchParams();
  if (next.tab && next.tab !== "coverage") params.set("tab", next.tab);
  if (next.account) params.set("account", next.account);
  if (next.region) params.set("region", next.region);
  if (next.engine) params.set("engine", next.engine);
  if (next.family) params.set("family", next.family);
  if (next.instanceClass) params.set("instance_class", next.instanceClass);
  if (next.coverageStatus) params.set("coverage", next.coverageStatus.toLowerCase());
  if (next.reservationStatus) params.set("reservation_status", next.reservationStatus);
  if (next.expirationRange) params.set("expiration", next.expirationRange);
  if (next.opportunityType) params.set("opportunity_type", next.opportunityType);
  if (next.opportunityStatus) params.set("opportunity_status", next.opportunityStatus);
  if (next.severity) params.set("severity", next.severity);
  if (next.page && next.page !== 1) params.set("page", String(next.page));
  if (next.pageSize && next.pageSize !== 50) params.set("page_size", String(next.pageSize));
  if (next.sort) params.set("sort", next.sort);
  if (next.order === "desc") params.set("order", "desc");
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function buildRdsDashboardQuery(state, kind) {
  const params = new URLSearchParams();
  const common = [
    ["account", state.account],
    ["region", state.region],
    ["engine", state.engine],
    ["family", state.family],
    ["instance_class", state.instanceClass],
  ];
  for (const [key, value] of common) if (value) params.set(key, value);
  if (kind !== "summary" && kind !== "options") {
    params.set("page", String(state.page || 1));
    params.set("page_size", String(state.pageSize || 50));
  }
  if (kind === "coverage") {
    if (state.coverageStatus) params.set("coverage_status", state.coverageStatus);
    params.set("sort", state.sort || "account");
    params.set("order", state.order || "asc");
  }
  if (kind === "reservations") {
    if (state.reservationStatus) params.set("reservation_status", state.reservationStatus);
    if (state.expirationRange) params.set("expiration_range", state.expirationRange);
    params.set("sort", state.sort || "expiration");
    params.set("order", state.order || "asc");
  }
  if (kind === "expiring") {
    params.set("expiration_range", state.expirationRange || "LE_30");
    params.set("sort", "expiration");
    params.set("order", "asc");
  }
  if (kind === "opportunities") {
    if (state.opportunityType) params.set("opportunity_type", state.opportunityType);
    if (state.opportunityStatus) params.set("opportunity_status", state.opportunityStatus);
    if (state.severity) params.set("severity", state.severity);
    params.set("sort", state.sort || "last_seen");
    params.set("order", state.sort ? (state.order || "desc") : "desc");
  }
  return params.toString();
}

export function coverageStatusLabel(value) {
  return {
    FULL: "Full",
    PARTIAL: "Partial",
    UNCOVERED: "Uncovered",
    UNKNOWN: "Unable to determine",
  }[String(value || "").toUpperCase()] || value || "Unknown";
}

export function opportunityTypeLabel(value) {
  return {
    RDS_RESERVATION_UNCOVERED: "Uncovered RDS",
    RDS_RESERVATION_PARTIAL_COVERAGE: "Partial coverage",
    RDS_RESERVATION_UNUSED_CAPACITY: "Unused capacity",
    RDS_RESERVATION_EXPIRING: "Expiring reservation",
  }[value] || value;
}

export function formatNu(value) {
  const number = Number(value || 0);
  return `${number.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} NU`;
}

export function clampPercentage(value) {
  const number = Number(value || 0);
  return Math.max(0, Math.min(100, Number.isFinite(number) ? number : 0));
}

export function coverageDisplayModel(item) {
  const required = Number(item?.required_units || 0);
  const covered = Number(item?.covered_units || 0);
  const status = String(item?.coverage_status || "UNKNOWN").toUpperCase();
  return {
    status,
    label: coverageStatusLabel(status),
    percentage: clampPercentage(item?.coverage_percentage || 0),
    capacity: `${formatNu(covered)} / ${formatNu(required)}`,
    uncovered: formatNu(Math.max(0, required - covered)),
    tone: status === "FULL" ? "positive" : status === "PARTIAL" ? "warning" : status === "UNCOVERED" ? "critical" : "neutral",
  };
}

export function reservationUtilizationDisplay(item) {
  const total = Number(item?.total_capacity || 0);
  const allocated = Number(item?.allocated_capacity || 0);
  const unused = Number(item?.unused_capacity || 0);
  return {
    percentage: clampPercentage(item?.utilization_percentage || 0),
    capacity: `${formatNu(allocated)} / ${formatNu(total)}`,
    unused: formatNu(unused),
  };
}

export function crossAccountLabel(scope) {
  const value = String(scope || "").toUpperCase();
  if (value.includes("POTENTIAL")) return "Potential";
  if (value.includes("CROSS_ACCOUNT")) return "Cross-account · Verified";
  return value ? value.toLowerCase().split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ") : "—";
}
