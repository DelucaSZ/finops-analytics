import {formatLocaleCurrency, formatLocaleNumber} from "../i18n/formatters.mjs";
export const PROVIDER_LABELS = Object.freeze({
  aws: "AWS",
  oci: "OCI",
  azure: "Azure",
  gcp: "GCP",
});

export function providerLabel(provider) {
  const key = String(provider || "").trim().toLowerCase();
  return PROVIDER_LABELS[key] || (key ? key.toUpperCase() : "—");
}

export function formatMoney(value, currency = "USD", locale = "pt-BR") {
  return formatLocaleCurrency(value, currency, locale, {minimumFractionDigits: 2});
}

export function formatNumber(value, locale = "pt-BR") {
  return formatLocaleNumber(value, locale);
}

export function formatAccountLabel(accountName, accountId) {
  const name = String(accountName || "").trim();
  const id = String(accountId || "").trim();
  if (name && id && name !== id) return `${name} · ${id}`;
  return name || id || "—";
}
