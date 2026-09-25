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

export type EvidenceMetric = {
  key: string;
  label: string;
  value: unknown;
  unit: string | null;
  currency: string | null;
  kind: string;
};

export type EvidenceCriterion = {
  key: string;
  label: string;
  operator: string | null;
  value: unknown;
  unit: string | null;
  currency: string | null;
};

export type RuleExplanation = {
  key: string;
  name: string;
  description: string;
  criteria: EvidenceCriterion[];
};

export type OpportunityEvidence = {
  schema_version: number;
  summary: string;
  metrics: EvidenceMetric[];
  details: Record<string, unknown>;
  rule: RuleExplanation;
  decision_parameters: Record<string, unknown>;
  source: {
    provider: string;
    system: string;
    evaluated_at: string;
  };
  limitations: string[];
};

export type Finding = {
  id: string;
  fingerprint: string;
  provider: string;
  account_id: string;
  account_name: string;
  legacy_account_id: number;
  rule_key: string;
  service: string;
  region: string;
  resource_id: string;
  resource_name: string | null;
  title: string;
  description: string;
  evidence?: OpportunityEvidence | Record<string, unknown>;
  current_monthly_cost: string;
  estimated_monthly_savings: string;
  confidence: string;
  severity: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  needs_review: boolean;
};

export type OpportunityPage = {
  items: Finding[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type OpportunityDetail = Finding & {
  scan_id: string;
  evidence: OpportunityEvidence | Record<string, unknown>;
  latest_observation: OpportunityObservation | null;
  rule: RuleExplanation;
  treated_at: string | null;
  treated_by: string | null;
  treatment_note: string | null;
  rejected_at: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
};

export type OpportunityStats = {
  open: number;
  treated: number;
  rejected: number;
};

export type OpportunityObservation = {
  id: string;
  collection_run_id: string;
  observed_at: string;
  severity: string;
  current_monthly_cost: string;
  estimated_monthly_savings: string;
  confidence: string;
  evidence: OpportunityEvidence | Record<string, unknown>;
  collection_provider: string;
  collection_account_id: string;
  collection_started_at: string;
  collection_finished_at: string | null;
  collection_status: string;
};

export type OpportunityObservationPage = {
  items: OpportunityObservation[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type OpportunityStatusHistoryEntry = {
  id: string;
  from_status: string;
  to_status: string;
  action: string;
  reason: string | null;
  note: string | null;
  changed_by: string | null;
  changed_by_name: string | null;
  changed_at: string;
};

export type OpportunityStatusHistoryPage = {
  items: OpportunityStatusHistoryEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type CollectionRun = {
  id: string;
  scan_id: string | null;
  provider: string;
  account_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  resources_analyzed: number;
  opportunities_found: number;
  analyzer_version: string | null;
  error_detail: string | null;
  created_at: string;
  updated_at: string;
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
