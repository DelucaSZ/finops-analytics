import { api } from "./api";

export type BillingGranularity = "DAILY" | "MONTHLY";
export type BillingMetric = "AMORTIZED_COST" | "NET_AMORTIZED_COST" | "UNBLENDED_COST";
export type BillingGroupBy = "NONE" | "SERVICE" | "ACCOUNT";

export type AwsBillingRequest = {
  account_ids: number[];
  start_date: string;
  end_date: string;
  granularity?: BillingGranularity;
  metric?: BillingMetric;
  group_by?: BillingGroupBy;
  exclude_record_types?: string[];
};

export type BillingSummaryTotal = {
  amount: string;
  currency: string;
  estimated: boolean;
};

export type BillingSummaryResponse = {
  metric: BillingMetric;
  start_date: string;
  end_date: string;
  totals: BillingSummaryTotal[];
};

export type BillingSeriesPoint = BillingSummaryTotal & {
  start_date: string;
  end_date: string;
};

export type BillingTimeSeriesResponse = {
  metric: BillingMetric;
  granularity: BillingGranularity;
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

export type BillingBreakdownResponse = {
  metric: BillingMetric;
  group_by: BillingGroupBy;
  start_date: string;
  end_date: string;
  items: BillingBreakdownItem[];
};

function postBilling<T>(path: string, request: AwsBillingRequest): Promise<T> {
  return api<T>(path, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getAwsBillingSummary(
  request: AwsBillingRequest,
): Promise<BillingSummaryResponse> {
  return postBilling<BillingSummaryResponse>("/billing/aws/summary", {
    ...request,
    group_by: "NONE",
  });
}

export function getAwsBillingTimeSeries(
  request: AwsBillingRequest,
): Promise<BillingTimeSeriesResponse> {
  return postBilling<BillingTimeSeriesResponse>("/billing/aws/timeseries", {
    ...request,
    group_by: "NONE",
  });
}

export function getAwsBillingBreakdown(
  request: AwsBillingRequest & { group_by: Exclude<BillingGroupBy, "NONE"> },
): Promise<BillingBreakdownResponse> {
  return postBilling<BillingBreakdownResponse>("/billing/aws/breakdown", request);
}
