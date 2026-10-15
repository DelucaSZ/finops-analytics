export type BillingPeriodPreset =
  | "this_month"
  | "previous_month"
  | "last_30_days"
  | "last_3_months"
  | "last_6_months"
  | "this_year"
  | "custom";

export type BillingPeriod = { start_date: string; end_date: string };

export const BILLING_PERIOD_PRESETS: Array<{ value: BillingPeriodPreset; label: string }>;

export function resolveBillingPeriod(
  preset: BillingPeriodPreset,
  options?: { customFrom?: string; customTo?: string; now?: Date },
): BillingPeriod | null;

export function previousEquivalentPeriod(
  period: BillingPeriod,
  preset: BillingPeriodPreset,
): BillingPeriod | null;

export function inclusiveEndDate(endExclusive: string): string;

export function billingVariation(
  currentValue: string | number,
  previousValue: string | number,
): { kind: "percent" | "new" | "unavailable"; percent: number | null };

export function formatBillingMoney(
  amount: string | number,
  currency: string,
  locale?: string,
): string;

export function formatBillingDate(value: string, locale?: string): string;
export function formatBillingRange(period: BillingPeriod | null, locale?: string): string;
export function sameStringSet(left: string[], right: string[]): boolean;

export function topBillingItems<T extends { amount: string | number; label: string }>(
  items: T[],
  limit?: number,
): T[];

export function groupBillingByCurrency<T extends { currency: string }>(
  items: T[],
): Array<[string, T[]]>;

export function billingQuerySignature(input: {
  profileId: string;
  accountIds: number[];
  period: BillingPeriod | null;
  metric: string;
  granularity: string;
  excludeRecordTypes: string[];
  revision?: number;
}): string;
