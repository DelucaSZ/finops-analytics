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

export type AwsAccountConfiguration = {
  id: number;
  role_arn: string;
  external_id: string;
  regions: string[];
  is_management_account: boolean;
  schedule_enabled: boolean;
  scan_interval_hours: number;
  next_scan_at: string | null;
  created_at: string;
  updated_at: string;
};

export type OciAccountConfiguration = {
  id: number;
  user_ocid: string;
  fingerprint: string;
  region: string;
  scope_regions: string[];
  compartment_ocids: string[];
  include_root_compartment: boolean;
  include_subcompartments: boolean;
  credentials_configured: boolean;
  credential_key_version: string | null;
  credential_revision: number;
  configuration_revision: number;
  created_at: string;
  updated_at: string;
};

export type CloudAccount = {
  id: number;
  provider: string;
  native_account_id: string;
  name: string;
  enabled: boolean;
  connection_status: "untested" | "connected" | "error";
  last_connection_test_at: string | null;
  last_error: string | null;
  created_at: string;
  updated_at: string;
  aws_configuration: AwsAccountConfiguration | null;
  oci_configuration: OciAccountConfiguration | null;
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
  account_name: string | null;
  legacy_account_id: number | null;
  rule_key: string;
  service: string;
  region: string | null;
  resource_id: string;
  resource_name: string | null;
  resource_type: string | null;
  provider_metadata: Record<string, unknown>;
  title: string;
  description: string;
  current_monthly_cost: string;
  estimated_monthly_savings: string;
  currency: string;
  confidence: string;
  severity: string;
  status: string;
  first_seen_at: string;
  last_seen_at: string;
  total_occurrence_count: number;
  needs_review: boolean;
};

export type OpportunityPage = {
  items: Finding[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type OpportunityOptions = {
  providers: string[];
  accounts: { provider: string; account_id: string; account_name: string | null }[];
  regions: string[];
  services: string[];
  resource_types: string[];
  rules: string[];
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
  scan_id: string | null;
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
  currency: string;
  confidence: string;
  provider_metadata: Record<string, unknown>;
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
  retained_total: number;
  total_occurrence_count: number;
  history_complete: boolean;
  retention_enabled: boolean;
  retention_days: number;
  retention_cutoff: string;
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
  scope: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  status: string;
  resources_analyzed: number;
  opportunities_found: number;
  detailed_observations_available: boolean;
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
  scope: {
    provider: string | null;
    account_id: string | null;
    valid_scope_count: number;
    has_current_data: boolean;
  };
  opportunities: {
    open: number;
    treated: number;
    rejected: number;
    new_since_previous: number;
  };
  severity: {
    high: number;
    medium: number;
    low: number;
    other: number;
  };
  financial: {
    metric: string;
    label: string;
    period: string;
    totals: Array<{ currency: string; amount: string }>;
  };
  by_provider: Array<{
    provider: string;
    open: number;
    estimated_monthly_savings: string | null;
    currency: string | null;
  }>;
  by_account: Array<{
    provider: string;
    account_id: string;
    account_name: string | null;
    open: number;
    estimated_monthly_savings: string | null;
    currency: string | null;
  }>;
  top_opportunities: Array<{
    id: string;
    title: string;
    rule_key: string;
    resource_id: string;
    resource_name: string | null;
    region: string | null;
    provider: string;
    account_id: string;
    account_name: string | null;
    collection_run_id: string;
    severity: string;
    estimated_monthly_savings: string;
    currency: string;
  }>;
  recent_changes: {
    new: number;
    no_longer_detected: number;
    changed: number | null;
    changed_available: boolean;
    comparable_scopes: number;
    scopes_without_baseline: number;
    rules_version_changed_scopes: number;
    rules_version_unknown_scopes: number;
  };
};

export type DashboardCollectionHealth = {
  scope: {
    provider: string | null;
    account_id: string | null;
  };
  total_scopes: number;
  valid_scopes: number;
  latest_execution: {
    failed: number;
    running: number;
    success: number;
  };
  valid_with_warnings: number;
  newest_valid_at: string | null;
  oldest_valid_at: string | null;
  oldest_valid_scope: {
    provider: string;
    account_id: string;
    account_name: string | null;
    started_at: string;
  } | null;
  stale_policy_configured: boolean;
  items: Array<{
    provider: string;
    account_id: string;
    account_name: string | null;
    latest_execution: {
      id: string;
      status: string;
      started_at: string;
      finished_at: string | null;
      has_warnings: boolean;
    };
    latest_valid: {
      id: string;
      status: string;
      started_at: string;
      finished_at: string | null;
      rules_version: string | null;
      has_warnings: boolean;
    } | null;
  }>;
};

export type CollectionItem = CollectionRun & {
  account_name: string | null;
  duration_seconds: number | null;
  resources_analyzed_available: boolean;
  has_warnings: boolean;
};
export type CollectionPage = {
  items: CollectionItem[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  account_summary: { latest_run: CollectionItem | null; latest_success: CollectionItem | null } | null;
};
export type CollectionDetail = CollectionItem & {
  opportunities_observed: number;
  warning_detail: string | null;
  trigger: string | null;
};
export type CollectionOptions = {
  providers: string[];
  accounts: { provider: string; account_id: string; account_name: string | null }[];
  has_more_accounts: boolean;
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
  detailed_observations_available: boolean;
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
  currency: string;
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
  resource_type: string | null;
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
