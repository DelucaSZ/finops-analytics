export type AwsAccount = {
  id: number;
  name: string;
  aws_account_id: string;
  role_arn: string;
  external_id: string;
  regions: string[];
  enabled: boolean;
  is_management_account: boolean;
  schedule_enabled: boolean;
  scan_interval_hours: number;
  connection_status: "untested" | "connected" | "error";
  last_connection_test_at: string | null;
  last_error: string | null;
  next_scan_at: string | null;
};

export type Policy = {
  rule_key: string;
  name: string;
  description: string;
  implemented: boolean;
  enabled: boolean;
  config: Record<string, unknown>;
  inherited: boolean;
  override_fields: string[];
};

export type Finding = {
  id: string;
  account_id: number;
  rule_key: string;
  service: string;
  region: string;
  resource_id: string;
  resource_name: string | null;
  title: string;
  description: string;
  evidence: Record<string, unknown>;
  current_monthly_cost: string;
  estimated_monthly_savings: string;
  confidence: string;
  severity: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  treated_at: string | null;
  treated_by: string | null;
  treatment_note: string | null;
  rejected_at: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  needs_review: boolean;
};

export type Scan = {
  id: string;
  account_id: number;
  status: string;
  trigger: string;
  started_at: string | null;
  completed_at: string | null;
  findings_count: number;
  error: string | null;
  created_at: string;
};

export type DashboardSummary = {
  accounts: number;
  connected_accounts: number;
  open_findings: number;
  estimated_monthly_savings_usd: number;
  estimated_annual_savings_usd: number;
  by_severity: Record<string, number>;
  latest_scans: Array<{
    id: string;
    account_id: number;
    status: string;
    created_at: string;
    findings_count: number;
  }>;
  top_findings: Array<{
    id: string;
    account_id: number;
    title: string;
    resource_id: string;
    region: string;
    severity: string;
    estimated_monthly_savings_usd: number;
  }>;
};
