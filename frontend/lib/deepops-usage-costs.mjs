export const USAGE_COST_PERIOD_PRESETS = [
  { value: "today", label: "Hoje" },
  { value: "last-7-days", label: "Últimos 7 dias" },
  { value: "this-month", label: "Este mês" },
  { value: "previous-month", label: "Mês anterior" },
  { value: "last-3-months", label: "Últimos 3 meses" },
  { value: "custom", label: "Personalizado" },
];

const COLLECTOR_LABELS = {
  rds_nonprod_idle: "RDS — ociosidade não produtiva",
  load_balancer_no_traffic: "Load Balancer — sem tráfego",
};

function pad(value) {
  return String(value).padStart(2, "0");
}

export function localDateKey(date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function localStart(year, month, day) {
  return new Date(year, month, day, 0, 0, 0, 0);
}

function addDays(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

export function resolveUsageCostPeriod(preset, customStart, customEnd, now = new Date()) {
  const today = localStart(now.getFullYear(), now.getMonth(), now.getDate());
  let start;
  let end;

  switch (preset) {
    case "today":
      start = today;
      end = addDays(today, 1);
      break;
    case "last-7-days":
      start = addDays(today, -6);
      end = addDays(today, 1);
      break;
    case "previous-month":
      start = localStart(now.getFullYear(), now.getMonth() - 1, 1);
      end = localStart(now.getFullYear(), now.getMonth(), 1);
      break;
    case "last-3-months":
      start = localStart(now.getFullYear(), now.getMonth() - 2, 1);
      end = localStart(now.getFullYear(), now.getMonth() + 1, 1);
      break;
    case "custom": {
      if (!customStart || !customEnd) return null;
      const [startYear, startMonth, startDay] = customStart.split("-").map(Number);
      const [endYear, endMonth, endDay] = customEnd.split("-").map(Number);
      start = localStart(startYear, startMonth - 1, startDay);
      end = addDays(localStart(endYear, endMonth - 1, endDay), 1);
      if (!(start < end)) return null;
      break;
    }
    case "this-month":
    default:
      start = localStart(now.getFullYear(), now.getMonth(), 1);
      end = localStart(now.getFullYear(), now.getMonth() + 1, 1);
      break;
  }

  return {
    date_from: start.toISOString(),
    date_to: end.toISOString(),
    start_key: localDateKey(start),
    end_key: localDateKey(addDays(end, -1)),
    days: Math.max(1, Math.round((end.getTime() - start.getTime()) / 86_400_000)),
  };
}

export function usageCostGranularity(period) {
  return period && period.days > 62 ? "monthly" : "daily";
}

export function buildUsageCostQuery(filters, extra = {}) {
  const params = new URLSearchParams();
  const values = { ...filters, ...extra };
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function formatUsageCostMoney(value, currency) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${currency} —`;
  const absolute = Math.abs(amount);
  let digits = 2;
  if (absolute > 0 && absolute < 0.01) digits = 4;
  if (absolute > 0 && absolute < 0.0001) digits = 6;
  if (absolute > 0 && absolute < 0.000001) digits = 8;

  const formatter = new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency,
    currencyDisplay: "symbol",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const formatted = formatter.format(amount);
  if (amount !== 0 && Number(amount.toFixed(digits)) === 0) {
    return `< ${formatter.format(10 ** -digits)}`;
  }
  return formatted;
}

export function formatUsageNumber(value) {
  return new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 }).format(Number(value) || 0);
}

export function formatUsageCostDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatUsagePeriodLabel(period) {
  if (!period) return "Período inválido";
  const format = (key) => {
    const [year, month, day] = key.split("-").map(Number);
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "medium" }).format(
      new Date(year, month - 1, day),
    );
  };
  return period.start_key === period.end_key
    ? format(period.start_key)
    : `${format(period.start_key)} a ${format(period.end_key)}`;
}

export function summarizeUsage(items) {
  return items.reduce(
    (total, item) => ({
      events: total.events + Number(item.events || 0),
      requests: total.requests + Number(item.requests || 0),
      metric_queries: total.metric_queries + Number(item.metric_queries || 0),
      metrics_requested: total.metrics_requested + Number(item.metrics_requested || 0),
      failed_events: total.failed_events + Number(item.failed_events || 0),
    }),
    { events: 0, requests: 0, metric_queries: 0, metrics_requested: 0, failed_events: 0 },
  );
}

export function usageByGroup(items) {
  return new Map(items.map((item) => [item.group ?? null, item]));
}

export function costItemsByCurrency(items) {
  const groups = new Map();
  for (const item of items) {
    const rows = groups.get(item.currency) || [];
    rows.push(item);
    groups.set(item.currency, rows);
  }
  for (const rows of groups.values()) {
    rows.sort((left, right) => Number(right.gross_estimated_cost) - Number(left.gross_estimated_cost));
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right));
}

export function friendlyUsageLabel(value, kind = "generic") {
  if (value === null || value === undefined || value === "") {
    return kind === "analyzer" ? "Compartilhado / não atribuído" : "Não atribuído";
  }
  if (value === "Shared / Unattributed") return "Compartilhado / não atribuído";
  if ((kind === "collector" || kind === "analyzer") && COLLECTOR_LABELS[value]) {
    return COLLECTOR_LABELS[value];
  }
  if (kind === "collector" || kind === "analyzer") {
    return String(value)
      .split("_")
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }
  return String(value);
}

export function pricingVersionCount(items) {
  const versions = new Set();
  for (const item of items) {
    for (const component of item.components || []) {
      versions.add(`${component.pricing_rule_id}:${component.effective_from}`);
    }
  }
  return versions.size;
}

export function distinctUsageGroups(items) {
  return [...new Set(items.map((item) => item.group).filter((value) => value !== null && value !== undefined))]
    .map(String)
    .sort((left, right) => left.localeCompare(right));
}

export function costShare(item, currencyItems) {
  const total = currencyItems.reduce((sum, row) => sum + Number(row.gross_estimated_cost || 0), 0);
  if (!total) return null;
  return (Number(item.gross_estimated_cost || 0) / total) * 100;
}
