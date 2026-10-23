import { api } from "./api";

export type BillingGranularity = "DAILY" | "MONTHLY";
export type BillingMetric = "AMORTIZED_COST" | "NET_AMORTIZED_COST" | "UNBLENDED_COST";
export type BillingGroupBy = "NONE" | "SERVICE" | "ACCOUNT";
export type BillingDataStatus =
  | "ACTUAL"
  | "ESTIMATED"
  | "PARTIALLY_ESTIMATED"
  | "FORECAST"
  | "INCLUDES_FORECAST";

export type AwsBillingRequest = {
  account_ids: number[];
  start_date: string;
  end_date: string;
  profile_id?: string;
  granularity?: BillingGranularity;
  metric?: BillingMetric;
  group_by?: BillingGroupBy;
  exclude_record_types?: string[];
};

export type BillingProfile = {
  id: string;
  name: string;
  description: string | null;
  granularity: BillingGranularity;
  metric: BillingMetric;
  group_by: BillingGroupBy;
  exclude_record_types: string[];
  is_default: boolean;
  enabled: boolean;
  is_system: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
};

export type BillingProfileInput = {
  name: string;
  description?: string | null;
  granularity: BillingGranularity;
  metric: BillingMetric;
  group_by: BillingGroupBy;
  exclude_record_types: string[];
  is_default?: boolean;
};

export type ResolvedBillingOptions = {
  granularity: BillingGranularity;
  metric: BillingMetric;
  group_by: BillingGroupBy;
  exclude_record_types: string[];
};

export type BillingProfileMetadata = {
  profile_id: string | null;
  profile_name: string | null;
  resolved_options: ResolvedBillingOptions | null;
};

export type BillingSummaryTotal = {
  amount: string;
  currency: string;
  status: BillingDataStatus;
  /** @deprecated Use status. This is derived by the backend for compatibility. */
  estimated: boolean;
};

export type BillingSummaryResponse = BillingProfileMetadata & {
  metric: BillingMetric;
  start_date: string;
  end_date: string;
  totals: BillingSummaryTotal[];
};

export type BillingSeriesGroup = BillingSummaryTotal & {
  key: string;
  label: string;
  deepops_account_id: number | null;
  aws_account_id: string | null;
  display_name: string | null;
};

export type BillingSeriesPoint = BillingSummaryTotal & {
  start_date: string;
  end_date: string;
  groups: BillingSeriesGroup[];
};

export type BillingTimeSeriesResponse = BillingProfileMetadata & {
  metric: BillingMetric;
  granularity: BillingGranularity;
  group_by: BillingGroupBy;
  start_date: string;
  end_date: string;
  points: BillingSeriesPoint[];
};

export type BillingBreakdownItem = BillingSummaryTotal & {
  key: string;
  label: string;
  deepops_account_id: number | null;
  aws_account_id: string | null;
  display_name: string | null;
};

export type BillingBreakdownResponse = BillingProfileMetadata & {
  metric: BillingMetric;
  group_by: BillingGroupBy;
  start_date: string;
  end_date: string;
  items: BillingBreakdownItem[];
};

function postBilling<T>(
  path: string,
  request: AwsBillingRequest,
  signal?: AbortSignal,
): Promise<T> {
  return api<T>(path, {
    method: "POST",
    body: JSON.stringify(request),
    signal,
  });
}

export function getAwsBillingSummary(
  request: AwsBillingRequest,
  signal?: AbortSignal,
): Promise<BillingSummaryResponse> {
  return postBilling<BillingSummaryResponse>("/billing/aws/summary", {
    ...request,
    group_by: "NONE",
  }, signal);
}

export function getAwsBillingTimeSeries(
  request: AwsBillingRequest,
  signal?: AbortSignal,
): Promise<BillingTimeSeriesResponse> {
  return postBilling<BillingTimeSeriesResponse>("/billing/aws/timeseries", request, signal);
}

export function getAwsBillingBreakdown(
  request: AwsBillingRequest & { group_by: Exclude<BillingGroupBy, "NONE"> },
  signal?: AbortSignal,
): Promise<BillingBreakdownResponse> {
  return postBilling<BillingBreakdownResponse>("/billing/aws/breakdown", request, signal);
}

export function listBillingProfiles(signal?: AbortSignal): Promise<BillingProfile[]> {
  return api<BillingProfile[]>("/billing/aws/profiles", { signal });
}

export function createBillingProfile(input: BillingProfileInput): Promise<BillingProfile> {
  return api<BillingProfile>("/billing/aws/profiles", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateBillingProfile(
  id: string,
  input: Partial<Omit<BillingProfileInput, "is_default">>,
): Promise<BillingProfile> {
  return api<BillingProfile>(`/billing/aws/profiles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export function setDefaultBillingProfile(id: string): Promise<BillingProfile> {
  return api<BillingProfile>(`/billing/aws/profiles/${id}/set-default`, { method: "POST" });
}

export function deactivateBillingProfile(id: string): Promise<BillingProfile> {
  return api<BillingProfile>(`/billing/aws/profiles/${id}/deactivate`, { method: "POST" });
}
