export type RdsCoverageStatus = "FULL" | "PARTIAL" | "UNCOVERED" | "UNKNOWN";

export type RdsAccountRef = {
  id: number | null;
  name: string | null;
  account_id: string;
};

export type RdsReservationAllocation = {
  allocation_id: number;
  reservation_id: string;
  reservation_db_id: number;
  reservation_account: RdsAccountRef;
  reservation_class: string;
  allocated_units: number;
  allocation_percentage: number;
  match_type: string;
  allocation_scope: string;
  reason: Record<string, unknown>;
};

export type RdsCoverageItem = {
  instance_id: number;
  instance: string;
  account: RdsAccountRef;
  region: string;
  engine: string;
  engine_version: string | null;
  instance_class: string;
  family: string;
  size: string;
  topology: string;
  multi_az: boolean;
  license_model: string | null;
  required_units: number;
  covered_units: number;
  uncovered_units: number;
  coverage_percentage: number;
  coverage_status: RdsCoverageStatus;
  coverage_scope: string;
  calculation_method: string;
  allocations: RdsReservationAllocation[];
  explanation: Record<string, unknown>;
  inventory_updated_at: string | null;
};

export type RdsReservationWorkload = {
  allocation_id: number;
  instance: string;
  instance_id: number;
  workload_account: RdsAccountRef;
  allocated_units: number;
  match_type: string;
  allocation_scope: string;
  reason: Record<string, unknown>;
};

export type RdsReservationUtilization = {
  reservation_id: number;
  reservation: string;
  offering_id: string | null;
  account: RdsAccountRef;
  region: string;
  engine: string;
  instance_class: string;
  family: string;
  size: string;
  quantity: number;
  multi_az: boolean;
  offering_type: string | null;
  offering_class: string | null;
  currency: string | null;
  fixed_price: number;
  recurring_charges: unknown;
  state: string;
  start_time: string;
  expiration_at: string;
  days_remaining: number;
  total_capacity: number;
  allocated_capacity: number;
  unused_capacity: number;
  utilization_percentage: number;
  workloads: RdsReservationWorkload[];
  expiration_severity: string | null;
  expiration_band: string | null;
  recommended_action: string | null;
  inventory_updated_at: string | null;
};

export type RdsReservationOpportunity = {
  id: string;
  type: string;
  resource: string;
  resource_id: string;
  resource_type: string | null;
  account_id: string;
  account_name: string | null;
  region: string | null;
  severity: string;
  status: string;
  presence_status: string;
  first_seen_at: string;
  last_seen_at: string;
  title: string;
  description: string;
  recommended_action: string | null;
  metadata: Record<string, unknown>;
};

export type RdsReservationsSummary = {
  coverage_run_id: number;
  rds: {
    total: number;
    fully_covered: number;
    partially_covered: number;
    uncovered: number;
    unknown: number;
  };
  coverage: {
    required_units: number;
    covered_units: number;
    uncovered_units: number;
    coverage_percentage: number;
  };
  reservations: {
    active: number;
    reserved_units: number;
    used_units: number;
    unused_units: number;
    utilization_percentage: number;
  };
  expiring_next_30_days: number;
  billing: {
    technical_coverage_percentage: number;
    aws_observed_coverage_percentage: number | null;
    validation_status: string;
    reconciliation_status: string;
    reconciliation_detail: string | null;
  };
  freshness: {
    inventory_updated_at: string | null;
    coverage_calculated_at: string | null;
    billing_data_reference: string | null;
  };
};

export type RdsReservationsOperationalStatus = {
  last_inventory_collection_at: string | null;
  last_coverage_run_at: string | null;
  last_successful_coverage_run_at: string | null;
  coverage_run_id: number | null;
  latest_run_id: number | null;
  pipeline_status: "NEVER_EXECUTED" | "RUNNING" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "FAILED" | "STALE";
  pipeline_stage: string | null;
  inventory_status: string;
  coverage_status: string;
  opportunity_status: string;
  billing_validation_status: string;
  data_freshness: "FRESH" | "STALE" | "UNKNOWN";
  freshness_threshold_hours: number;
  error_detail: string | null;
};

export type RdsReservationsOptions = {
  accounts: RdsAccountRef[];
  regions: string[];
  engines: string[];
  families: string[];
  instance_classes: string[];
};

export type RdsPage<T> = {
  coverage_run_id?: number;
  items: T[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};
