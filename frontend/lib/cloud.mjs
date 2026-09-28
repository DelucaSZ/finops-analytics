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
  const numeric = Number(value);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency || "USD",
      minimumFractionDigits: 2,
    }).format(Number.isFinite(numeric) ? numeric : 0);
  } catch {
    return `${currency || "—"} ${(Number.isFinite(numeric) ? numeric : 0).toLocaleString(locale, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`;
  }
}
