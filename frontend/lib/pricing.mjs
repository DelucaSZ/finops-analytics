import {formatLocaleCurrency} from "../i18n/formatters.mjs";
export function normalizeDecimalInput(value) {
  const normalized = String(value ?? "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,8})?$/.test(normalized)) return null;
  return normalized;
}

export function pricingLifecycleStatus(item, now = new Date()) {
  if (!item.enabled) return "inactive";
  const reference = now instanceof Date ? now.getTime() : new Date(now).getTime();
  const from = new Date(item.effective_from).getTime();
  const until = item.effective_until ? new Date(item.effective_until).getTime() : null;
  if (from > reference) return "future";
  if (until !== null && until <= reference) return "expired";
  return "active";
}

export function pricingStatusLabel(status) {
  return {
    active: "Ativo",
    inactive: "Inativo",
    future: "Futuro",
    expired: "Expirado",
  }[status] || status;
}

export function unitLabel(unit) {
  return {
    OCPU_HOUR: "OCPU / hora",
    GB_RAM_HOUR: "GB RAM / hora",
    GB_MONTH: "GB / mês",
    VPU_GB_MONTH: "VPU / GB / mês",
    INSTANCE_HOUR: "Instância / hora",
  }[unit] || unit.replaceAll("_", " ");
}

export function sourceLabel(source) {
  return {
    IMPORTED_OCI_CALCULATOR: "Calculadora OCI importada",
    MANUAL: "Manual",
  }[source] || source.replaceAll("_", " ");
}

// Preserve the exact decimal string returned by OCI pricing (up to 8 places).
export function formatBrlDecimal(value, locale = "pt-BR") {
  return formatLocaleCurrency(value ?? "0", "BRL", locale, {
    minimumFractionDigits: 2, maximumFractionDigits: 8,
  });
}

export function toDatetimeLocal(value = new Date()) {
  const date = value instanceof Date ? value : new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function datetimeLocalToIso(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}
