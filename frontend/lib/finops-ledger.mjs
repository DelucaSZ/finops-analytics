export const MANUAL_ENTRY_TYPES = ["SAVING", "REALLOCATION", "ADJUSTMENT"];

export function directionForEntryType(entryType, adjustmentDirection = "CREDIT") {
  if (entryType === "SAVING") return "CREDIT";
  if (entryType === "REALLOCATION") return "DEBIT";
  if (entryType === "ADJUSTMENT") return adjustmentDirection;
  throw new Error(`Unsupported entry type: ${entryType}`);
}

export function defaultCurrencyForProvider(provider, current = "USD") {
  const normalized = String(provider || "").trim().toLowerCase();
  if (normalized === "aws") return "USD";
  if (normalized === "oci") return "BRL";
  return current;
}

export function accountsForProvider(accounts, provider) {
  const normalized = String(provider || "").trim().toLowerCase();
  return accounts.filter((account) => String(account.provider).trim().toLowerCase() === normalized);
}

export function normalizePositiveDecimal(value) {
  const normalized = String(value || "").trim().replace(",", ".");
  if (!/^\d+(?:\.\d{1,8})?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  if (!/[1-9]/.test(`${whole}${fraction}`)) return null;
  return normalized;
}

export function formatLedgerMoney(value, currency) {
  const normalized = String(value || "0").trim();
  const match = normalized.match(/^(\d+)(?:\.(\d+))?$/);
  if (!match) return `${currency} ${normalized}`;
  const whole = match[1].replace(/^0+(?=\d)/, "") || "0";
  const cents = `${match[2] || ""}00`.slice(0, 2);
  if (currency === "BRL") {
    return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ".")},${cents}`;
  }
  if (currency === "USD") {
    return `US$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${cents}`;
  }
  return `${currency} ${whole}.${cents}`;
}

export function sourceLabel(source) {
  if (source === "OPPORTUNITY") return "Oportunidade";
  if (source === "MANUAL") return "Manual";
  if (source === "SYSTEM") return "Sistema";
  return source;
}
