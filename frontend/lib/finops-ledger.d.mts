export const MANUAL_ENTRY_TYPES: readonly ["SAVING", "REALLOCATION", "ADJUSTMENT"];

export function directionForEntryType(
  entryType: string,
  adjustmentDirection?: "CREDIT" | "DEBIT",
): "CREDIT" | "DEBIT";

export function defaultCurrencyForProvider(
  provider: string,
  current?: "BRL" | "USD",
): "BRL" | "USD";

export function accountsForProvider<T extends { provider: string }>(
  accounts: T[],
  provider: string,
): T[];

export function normalizePositiveDecimal(value: string): string | null;

export function formatLedgerMoney(value: string, currency: string): string;

export function sourceLabel(source: string): string;
