// Presentation-only formatters. Locale never changes API values, currency, or time zone.
export const DEFAULT_FORMAT_LOCALE = "pt-BR";
export const DISPLAY_TIME_ZONE = "UTC";

function normalizedLocale(locale) {
  return locale === "en-US" ? "en-US" : DEFAULT_FORMAT_LOCALE;
}

function isInvalid(value) {
  return value === null || value === undefined || value === ""
    || (typeof value === "number" && !Number.isFinite(value));
}

function numericInput(value) {
  if (isInvalid(value)) return null;
  if (typeof value === "bigint") return value;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/.test(value.trim())) {
    // Intl.NumberFormat accepts decimal strings without a Number() precision loss.
    return value.trim();
  }
  return null;
}

export function formatLocaleNumber(value, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  const number = numericInput(value);
  return number === null ? "—" : new Intl.NumberFormat(normalizedLocale(locale), options).format(number);
}

export function formatLocaleCurrency(value, currency, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  const number = numericInput(value);
  if (number === null) return "—";
  const unit = String(currency || "").trim().toUpperCase();
  if (!unit) return formatLocaleNumber(number, locale, options);
  try {
    return new Intl.NumberFormat(normalizedLocale(locale), {
      style: "currency", currency: unit, ...options,
    }).format(number);
  } catch {
    return unit + " " + formatLocaleNumber(number, locale, options);
  }
}

// Backends can send points (12.5) or fractions (0.125). Never infer the scale.
export function formatLocalePercentage(value, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  const { valueMode = "points", ...numberOptions } = options;
  if (numericInput(value) === null) return "—";
  const fraction = valueMode === "fraction" ? value : Number(value) / 100;
  return new Intl.NumberFormat(normalizedLocale(locale), {
    style: "percent", maximumFractionDigits: 2, ...numberOptions,
  }).format(fraction);
}

function calendarDate(value) {
  if (typeof value !== "string") return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const year = Number(match[1]), month = Number(match[2]), day = Number(match[3]);
  const result = new Date(Date.UTC(0, month - 1, day, 12));
  result.setUTCFullYear(year);
  return result.getUTCFullYear() === year && result.getUTCMonth() === month - 1
    && result.getUTCDate() === day ? result : null;
}

// Date-only is a calendar label, not an instant. UTC is a rendering anchor.
export function formatLocaleDate(value, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  if (isInvalid(value)) return "—";
  const date = calendarDate(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !date) return "—";
  if (!date) return formatLocaleDateTime(value, locale, { dateStyle: "short", timeStyle: undefined, ...options });
  return new Intl.DateTimeFormat(normalizedLocale(locale), {
    dateStyle: "short", ...options, timeZone: "UTC",
  }).format(date);
}

// UTC is an explicit, deterministic default; callers may supply business timeZone.
export function formatLocaleDateTime(value, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  if (isInvalid(value)) return "—";
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return formatLocaleDate(value, locale, options);
  }
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(normalizedLocale(locale), {
    dateStyle: "short", timeStyle: "short", timeZone: DISPLAY_TIME_ZONE, ...options,
  }).format(date);
}

export function formatLocaleDuration(value, unit = "second", locale = DEFAULT_FORMAT_LOCALE) {
  const number = numericInput(value);
  if (number === null) return "—";
  return new Intl.NumberFormat(normalizedLocale(locale), {
    style: "unit", unit, unitDisplay: "long",
    maximumFractionDigits: 2,
  }).format(number);
}

export function formatLocaleRelative(value, unit, locale = DEFAULT_FORMAT_LOCALE, options = {}) {
  const number = numericInput(value);
  if (number === null) return "—";
  return new Intl.RelativeTimeFormat(normalizedLocale(locale), { numeric: "always", ...options }).format(Number(number), unit);
}
