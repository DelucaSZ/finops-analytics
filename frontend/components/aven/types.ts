export type ProductStatus = "neutral" | "info" | "success" | "warning" | "danger" | "pending";
export type TrendDirection = "up" | "down" | "flat";
export type TrendSentiment = "positive" | "negative" | "neutral";

export interface ProductSelectorOption {
  value: string;
  label: string;
  description?: string;
  disabled?: boolean;
  searchTerms?: string[];
}

export interface AccountSelectorOption extends ProductSelectorOption {
  accountId?: string;
  provider?: string;
  environment?: string;
}

export interface DateRangeValue {
  startDate: string | null;
  endDate: string | null;
}

export interface DateRangePreset {
  value: string;
  label: string;
  range?: DateRangeValue;
}
