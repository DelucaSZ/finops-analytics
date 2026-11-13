import { formatLocaleCurrency } from "../i18n/formatters.mjs";

/** Format up to the 8 persisted decimal places without binary floating-point conversion. */
export function formatAwsPrice(value, locale = "pt-BR") {
  if (typeof value !== "string" || !/^\d+(?:\.\d{1,8})?$/.test(value)) return "—";
  const decimals = value.split(".")[1]?.length ?? 0;
  return formatLocaleCurrency(value, "USD", locale, {
    minimumFractionDigits: Math.max(2, decimals),
    maximumFractionDigits: 8,
  });
}
