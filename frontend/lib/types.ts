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

export type EvidenceMetric = {
  key: string;
  label: string;
  value: number | string | boolean;
  unit: string | null;
  kind: string;
};

export type EvidenceCriterion = {
  key: string;
  label: string;
  observed_value: number | string | boolean | null;
  operator: string;
  threshold_value: number | string | boolean;
  unit: string | null;
};

export type EvidenceContributor = {
  key: string;
  label: string;
  previous_value: number | null;
  current_value: number | null;
  delta: number;
  unit: string | null;
};

export type RuleExplanation = {
  key: string;
  name: string;
  description: string;
};

export type OpportunityEvidence = {
  schema_version: number;
  summary: string;
  metrics: EvidenceMetric[];
  criteria: EvidenceCriterion[];
  details: Record<string, unknown>;
  parameters: Record<string, unknown>;
  rule: RuleExplanation;
  source: string;
  notes: string[];
  contributors: EvidenceContributor[];
  evaluated_at: string | null;
};

export type OpportunityDetail = Finding & {
  scan_id: string;
  treated_at: string | null;
  treated_by: string | null;
  treatment_note: string | null;
  rejected_at: string | null;
  rejected_by: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  rule: RuleExplanation;
  latest_observation: OpportunityObservation | null;
  latest_evidence: OpportunityEvidence | null;
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
  evidence: OpportunityEvidence;
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

export type CollectionComparisonCategory =
  | "NEW"
  | "PERSISTENT"
  | "NO_LONGER_DETECTED"
  | "CHANGED";

export type CollectionComparisonRun = {
  id: string;
  provider: string;
  account_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  rules_version: string | null;
};

export type CollectionComparisonWarning = {
  code: string;
  message: string;
};

export type CollectionComparisonSummary = {
  baseline_total: number;
  target_total: number;
  new: number;
  persistent: number;
  no_longer_detected: number;
  changed: number;
};

export type CollectionComparisonFinancialSummary = {
  metric: "estimated_monthly_savings";
  label: string;
  currency: "USD";
  period: "month";
  baseline_total: string;
  target_total: string;
  delta: string;
  delta_percent: string | null;
};

export type CollectionComparisonObservation = {
  observed_at: string;
  severity: string;
  current_monthly_cost: string;
  estimated_monthly_savings: string;
  confidence: string;
  evidence_summary: string | null;
};

export type CollectionComparisonChange = {
  type: string;
  label: string;
  baseline: unknown;
  target: unknown;
  unit: string | null;
};

export type CollectionComparisonItem = {
  category: CollectionComparisonCategory;
  opportunity_id: string;
  fingerprint: string;
  title: string;
  rule_key: string;
  service: string;
  region: string;
  resource_id: string;
  resource_name: string | null;
  lifecycle_status: string;
  first_seen_at: string;
  baseline: CollectionComparisonObservation | null;
  target: CollectionComparisonObservation | null;
  change_types: string[];
  changes: CollectionComparisonChange[];
};

export type CollectionComparisonResponse = {
  available: boolean;
  reason: string | null;
  message: string | null;
  baseline: CollectionComparisonRun | null;
  target: CollectionComparisonRun;
  summary: CollectionComparisonSummary | null;
  financial_summary: CollectionComparisonFinancialSummary | null;
  rules_version_warning: CollectionComparisonWarning | null;
  warnings: CollectionComparisonWarning[];
  category: CollectionComparisonCategory;
  items: CollectionComparisonItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};
