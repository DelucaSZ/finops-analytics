export type UsageCostPeriod = {
  date_from: string;
  date_to: string;
  start_key: string;
  end_key: string;
  days: number;
};

export type UsageCostSummaryItem = {
  group: string | null;
  events: number;
  requests: number;
  metric_queries: number;
  metrics_requested: number;
  failed_events: number;
};

export type UsageCostItem = {
  group: string | null;
  period: string | null;
  currency: string;
  gross_estimated_cost: string;
  usage_quantity: string;
  components?: Array<{ pricing_rule_id: string; effective_from: string }>;
};

export const USAGE_COST_PERIOD_PRESETS: Array<{ value: string; label: string }>;
export function localDateKey(date: Date): string;
export function resolveUsageCostPeriod(
  preset: string,
  customStart?: string,
  customEnd?: string,
  now?: Date,
): UsageCostPeriod | null;
export function usageCostGranularity(period: UsageCostPeriod | null): "daily" | "monthly";
export function buildUsageCostQuery(
  filters: Record<string, string | number | null | undefined>,
  extra?: Record<string, string | number | null | undefined>,
): string;
export function formatUsageCostMoney(value: string | number, currency: string): string;
export function formatUsageNumber(value: string | number): string;
export function formatUsageCostDate(value: string | null | undefined): string;
export function formatUsagePeriodLabel(period: UsageCostPeriod | null): string;
export function summarizeUsage(items: UsageCostSummaryItem[]): Omit<UsageCostSummaryItem, "group">;
export function usageByGroup(items: UsageCostSummaryItem[]): Map<string | null, UsageCostSummaryItem>;
export function costItemsByCurrency<T extends UsageCostItem>(items: T[]): Array<[string, T[]]>;
export function friendlyUsageLabel(value: string | null | undefined, kind?: string): string;
export function pricingVersionCount(items: UsageCostItem[]): number;
export function distinctUsageGroups(items: UsageCostSummaryItem[]): string[];
export function costShare(item: UsageCostItem, currencyItems: UsageCostItem[]): number | null;
