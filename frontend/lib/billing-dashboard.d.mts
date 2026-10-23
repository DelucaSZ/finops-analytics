export type BillingPeriodPreset =
  | "this_month"
  | "previous_month"
  | "last_30_days"
  | "last_3_months"
  | "last_6_months"
  | "this_year"
  | "custom";

export type BillingDataStatus =
  | "ACTUAL"
  | "ESTIMATED"
  | "PARTIALLY_ESTIMATED"
  | "FORECAST"
  | "INCLUDES_FORECAST";

export type BillingPeriod = { start_date: string; end_date: string };

export type BillingChartSeries = {
  key: string;
  label: string;
  total: number;
};

export type BillingChartPeriodSeries = {
  key: string;
  label: string;
  amount: number;
  status: BillingDataStatus;
  estimated: boolean;
};

export type BillingChartPeriod = {
  start_date: string;
  end_date: string;
  total: number;
  status: BillingDataStatus;
  estimated: boolean;
  series: BillingChartPeriodSeries[];
};

export type BillingChartDataset = {
  currency: string;
  total: number;
  status: BillingDataStatus;
  estimated: boolean;
  series: BillingChartSeries[];
  periods: BillingChartPeriod[];
};

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

export function formatBillingAxisMoney(
  amount: string | number,
  currency: string,
  locale?: string,
): string;

export function formatBillingDate(value: string, locale?: string): string;
export function formatBillingAxisDate(
  value: string,
  granularity: string,
  locale?: string,
): string;
export function formatBillingRange(period: BillingPeriod | null, locale?: string): string;
export function sameStringSet(left: string[], right: string[]): boolean;
export function parseBillingAccountIds(value: string | null, availableAccountIds: number[]): number[];
export function hasBillingAccountSelection(accountIds: number[]): boolean;
export function areAllBillingAccountsSelected(
  availableAccountIds: number[],
  selectedAccountIds: number[],
): boolean;
export function billingAccountIdsForSelectAll(
  checked: boolean,
  availableAccountIds: number[],
): number[];

export function topBillingItems<T extends { amount: string | number; label: string }>(
  items: T[],
  limit?: number,
): T[];

export function groupBillingByCurrency<T extends { currency: string }>(
  items: T[],
): Array<[string, T[]]>;

export function normalizeBillingStatus(
  value: BillingDataStatus | { status?: BillingDataStatus; estimated?: boolean } | null | undefined,
): BillingDataStatus;
export function aggregateBillingStatuses(statuses: BillingDataStatus[]): BillingDataStatus;
export function billingStatusLabel(
  status: BillingDataStatus | { status?: BillingDataStatus; estimated?: boolean },
): string;
export function billingStatusIsEstimated(
  status: BillingDataStatus | { status?: BillingDataStatus; estimated?: boolean },
): boolean;
export function billingStatusHasForecast(
  status: BillingDataStatus | { status?: BillingDataStatus; estimated?: boolean },
): boolean;

export function mapBillingTimeSeriesToChartData(
  points: Array<{
    start_date: string;
    end_date: string;
    amount: string | number;
    currency: string;
    status?: BillingDataStatus;
    estimated?: boolean;
    groups?: Array<{
      key: string;
      label: string;
      amount: string | number;
      status?: BillingDataStatus;
      estimated?: boolean;
      display_name?: string | null;
      aws_account_id?: string | null;
    }>;
  }>,
  groupBy?: string,
): BillingChartDataset[];

export function billingQuerySignature(input: {
  profileId: string;
  accountIds: number[];
  period: BillingPeriod | null;
  metric: string;
  granularity: string;
  groupBy: string;
  excludeRecordTypes: string[];
  revision?: number;
}): string;
