export const BILLING_PERIOD_PRESETS = [
  { value: "this_month", label: "Este mês" },
  { value: "previous_month", label: "Mês anterior" },
  { value: "last_30_days", label: "Últimos 30 dias" },
  { value: "last_3_months", label: "Últimos 3 meses" },
  { value: "last_6_months", label: "Últimos 6 meses" },
  { value: "this_year", label: "Este ano" },
  { value: "custom", label: "Personalizado" },
];

function atLocalMidnight(value) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function dateKey(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseDateKey(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  if (!match) return null;
  const result = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  if (dateKey(result) !== value) return null;
  return result;
}

function addDays(value, days) {
  const result = new Date(value);
  result.setDate(result.getDate() + days);
  return result;
}

function shiftMonthsClamped(value, months) {
  const day = value.getDate();
  const result = new Date(value.getFullYear(), value.getMonth() + months, 1);
  const lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0).getDate();
  result.setDate(Math.min(day, lastDay));
  return result;
}

function shiftYearsClamped(value, years) {
  const month = value.getMonth();
  const day = value.getDate();
  const result = new Date(value.getFullYear() + years, month, 1);
  const lastDay = new Date(result.getFullYear(), month + 1, 0).getDate();
  result.setDate(Math.min(day, lastDay));
  return result;
}

export function resolveBillingPeriod(
  preset,
  { customFrom = "", customTo = "", now = new Date() } = {},
) {
  const today = atLocalMidnight(now);
  const tomorrow = addDays(today, 1);
  const year = today.getFullYear();
  const month = today.getMonth();
  let start;
  let endExclusive;

  switch (preset) {
    case "previous_month":
      start = new Date(year, month - 1, 1);
      endExclusive = new Date(year, month, 1);
      break;
    case "last_30_days":
      start = addDays(today, -29);
      endExclusive = tomorrow;
      break;
    case "last_3_months":
      start = new Date(year, month - 2, 1);
      endExclusive = tomorrow;
      break;
    case "last_6_months":
      start = new Date(year, month - 5, 1);
      endExclusive = tomorrow;
      break;
    case "this_year":
      start = new Date(year, 0, 1);
      endExclusive = tomorrow;
      break;
    case "custom": {
      const from = parseDateKey(customFrom);
      const to = parseDateKey(customTo);
      if (!from || !to || from > to || to > today) return null;
      start = from;
      endExclusive = addDays(to, 1);
      break;
    }
    case "this_month":
    default:
      start = new Date(year, month, 1);
      endExclusive = tomorrow;
      break;
  }

  return {
    start_date: dateKey(start),
    end_date: dateKey(endExclusive),
  };
}

export function previousEquivalentPeriod(period, preset) {
  const start = parseDateKey(period?.start_date);
  const endExclusive = parseDateKey(period?.end_date);
  if (!start || !endExclusive || start >= endExclusive) return null;

  if (preset === "this_month" || preset === "previous_month") {
    return {
      start_date: dateKey(shiftMonthsClamped(start, -1)),
      end_date: dateKey(shiftMonthsClamped(endExclusive, -1)),
    };
  }

  if (preset === "this_year") {
    return {
      start_date: dateKey(shiftYearsClamped(start, -1)),
      end_date: dateKey(shiftYearsClamped(endExclusive, -1)),
    };
  }

  const durationDays = Math.round((endExclusive.getTime() - start.getTime()) / 86_400_000);
  const previousStart = addDays(start, -durationDays);
  return {
    start_date: dateKey(previousStart),
    end_date: dateKey(start),
  };
}

export function inclusiveEndDate(endExclusive) {
  const parsed = parseDateKey(endExclusive);
  return parsed ? dateKey(addDays(parsed, -1)) : endExclusive;
}

export function billingVariation(currentValue, previousValue) {
  const current = Number(currentValue);
  const previous = Number(previousValue);
  if (!Number.isFinite(current) || !Number.isFinite(previous)) {
    return { kind: "unavailable", percent: null };
  }
  if (previous === 0) {
    if (current === 0) return { kind: "percent", percent: 0 };
    return { kind: "new", percent: null };
  }
  if (previous < 0) return { kind: "unavailable", percent: null };
  return {
    kind: "percent",
    percent: ((current - previous) / previous) * 100,
  };
}

export function formatBillingMoney(amount, currency, locale = "pt-BR") {
  const numeric = Number(amount);
  const unit = String(currency || "").trim().toUpperCase();
  if (!Number.isFinite(numeric)) return unit ? `${unit} ${amount}` : String(amount);
  if (unit) {
    try {
      return new Intl.NumberFormat(locale, {
        style: "currency",
        currency: unit,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(numeric);
    } catch {
      // Cost Explorer may return a non-ISO unit. Preserve it instead of inventing a currency.
    }
  }
  const formatted = new Intl.NumberFormat(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric);
  return unit ? `${unit} ${formatted}` : formatted;
}

export function formatBillingDate(value, locale = "pt-BR") {
  const parsed = parseDateKey(value);
  return parsed
    ? new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed)
    : value;
}

export function formatBillingRange(period, locale = "pt-BR") {
  if (!period) return "—";
  return `${formatBillingDate(period.start_date, locale)}–${formatBillingDate(inclusiveEndDate(period.end_date), locale)}`;
}

export function sameStringSet(left, right) {
  if (left.length !== right.length) return false;
  const a = [...left].sort();
  const b = [...right].sort();
  return a.every((value, index) => value === b[index]);
}

export function parseBillingAccountIds(value, availableAccountIds) {
  if (typeof value !== "string" || !value.trim()) return [];
  const available = new Set(availableAccountIds);
  return Array.from(
    new Set(
      value
        .split(",")
        .map((item) => Number(item.trim()))
        .filter((accountId) => Number.isInteger(accountId) && available.has(accountId)),
    ),
  ).sort((left, right) => left - right);
}

export function hasBillingAccountSelection(accountIds) {
  return accountIds.length > 0;
}

export function areAllBillingAccountsSelected(availableAccountIds, selectedAccountIds) {
  if (!availableAccountIds.length) return false;
  const selected = new Set(selectedAccountIds);
  return selected.size === availableAccountIds.length
    && availableAccountIds.every((accountId) => selected.has(accountId));
}

export function billingAccountIdsForSelectAll(checked, availableAccountIds) {
  return checked
    ? Array.from(new Set(availableAccountIds)).sort((left, right) => left - right)
    : [];
}

export function topBillingItems(items, limit = 10) {
  return [...items]
    .sort((left, right) => Number(right.amount) - Number(left.amount) || left.label.localeCompare(right.label))
    .slice(0, limit);
}

export function groupBillingByCurrency(items) {
  const groups = new Map();
  for (const item of items) {
    const currency = item.currency || "";
    const current = groups.get(currency) || [];
    current.push(item);
    groups.set(currency, current);
  }
  return Array.from(groups.entries()).sort(([left], [right]) => left.localeCompare(right));
}

export function billingQuerySignature({
  profileId,
  accountIds,
  period,
  metric,
  granularity,
  excludeRecordTypes,
  revision = 0,
}) {
  return JSON.stringify({
    profileId,
    accountIds: [...accountIds].sort((a, b) => a - b),
    startDate: period?.start_date || "",
    endDate: period?.end_date || "",
    metric,
    granularity,
    excludeRecordTypes: [...excludeRecordTypes].sort(),
    revision,
  });
}
