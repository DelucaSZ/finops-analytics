import { api } from "@/lib/api";

export type Provider = "aws" | "oci";
export type Service = "ec2" | "rds" | "compute" | "db_system";
export type PeriodMode = "monthly" | "hours" | "days" | "weeks" | "custom";
export type PricingStatus =
  | "priced" | "partially_priced" | "sku_missing" | "unsupported_configuration"
  | "price_not_effective" | "missing_configuration" | "invalid_combination"
  | "pricing_configuration_error";

export interface CalculatorPeriod {
  mode: PeriodMode;
  amount?: string;
  start_at?: string;
  end_at?: string;
}

export interface VolumeInput {
  size_gb: string;
  vpus_per_gb: string;
  count: number;
}

export interface AwsFinancial {
  discount_percent: string;
  conversion_enabled: boolean;
  usd_brl_rate?: string;
  tax_percent: string;
}

export type ResourceConfiguration =
  | { service: "ec2"; instance_type: string; operating_system: string; purchase_option: "on_demand"; tenancy: "shared"; root_volume_gb?: string; ebs_volume_type?: "gp2" | "gp3"; ebs_volume_count?: number; ebs_iops?: number; ebs_throughput_mbps?: number }
  | { service: "rds"; instance_class: string; engine: string; deployment: string; storage_type: "gp2" | "gp3"; allocated_storage_gb: string }
  | { service: "compute"; shape: string; ocpus: string; memory_gb: string; operating_system: "linux" | "windows"; boot_volume: { size_gb: string; vpus_per_gb: string; count: 1 }; block_volumes: Array<{ size_gb: string; vpus_per_gb: string; count: number }> }
  | { service: "db_system"; deployment_model: "base_database"; shape: string; edition: string; license_model: string; cpu_unit: "ECPU"; cpu_count: string; storage_gb: string };

export interface CalculatorRequest {
  provider: Provider;
  region: string;
  resource_configuration: ResourceConfiguration;
  quantity: number;
  period: CalculatorPeriod;
  aws_financial?: AwsFinancial;
}

export interface PriceComponent {
  service: string;
  sku: string;
  unit: string;
  description: string | null;
  pricing_status: PricingStatus | null;
  unit_price: string | null;
  monthly_units: string | null;
  period_units: string | null;
  monthly_original_cost: string | null;
  period_original_cost: string | null;
  currency: "USD" | "BRL";
  source: string | null;
  pricing_item_id: string | null;
  effective_from: string | null;
  effective_until: string | null;
}

export interface CalculatorEstimate {
  provider: Provider;
  service: Service;
  region: string;
  pricing_status: PricingStatus;
  pricing_currency: "USD" | "BRL";
  final_currency: "USD" | "BRL";
  pricing_source: string | null;
  pricing_reference_date: string | null;
  period_duration_hours: string | null;
  monthly_original_cost: string | null;
  period_original_cost: string | null;
  monthly_known_subtotal: string | null;
  period_known_subtotal: string | null;
  discount_percent: string | null;
  monthly_discount_amount: string | null;
  period_discount_amount: string | null;
  monthly_net_cost: string | null;
  period_net_cost: string | null;
  conversion_enabled: boolean;
  usd_brl_rate: string | null;
  tax_percent: string | null;
  monthly_converted_cost: string | null;
  period_converted_cost: string | null;
  monthly_tax_amount: string | null;
  period_tax_amount: string | null;
  monthly_final_cost: string | null;
  period_final_cost: string | null;
  pricing_components: PriceComponent[];
  missing_pricing_components: string[];
  warnings: string[];
}

export type AwsOption = {
  instance_type?: string;
  operating_system?: string;
  instance_class?: string;
  deployment?: string;
};
export interface AwsOptionsResponse {
  items: AwsOption[];
  total: number;
  status: string;
  supported_engines: string[];
  source?: string;
}
export interface OciComputeShape {
  shape: string;
  max_ocpus: number;
  max_memory_gb: number;
  max_memory_per_ocpu_gb: number;
  pricing_status: PricingStatus;
  region_availability_verified: boolean;
}
export interface OciDbOption {
  deployment_model: "base_database";
  shape: string;
  edition: string;
  license_model: string;
  cpu_unit: "ECPU";
  complete_price_available: boolean;
  components: Record<string, { sku: string; status: PricingStatus; unit: string; source_reference: string }>;
}
export interface OciComputeOptions {
  service: "compute";
  items: OciComputeShape[];
  operating_systems: string[];
  vpu_tiers: number[];
  region: string;
}
export interface OciDbOptions {
  service: "db_system";
  items: OciDbOption[];
  region: string;
  setup_required: boolean;
  new_provisioning_shape: string;
  capacity_unit: "ECPU";
}

export function fetchAwsRegions(signal?: AbortSignal) {
  return api<{ items: string[]; source: string }>("/calculator/aws/regions", { signal });
}
export function fetchAwsOptions(
  service: "ec2" | "rds", region: string, search: string, engine: string, signal?: AbortSignal,
) {
  const params = new URLSearchParams({ service, region, search, limit: "100" });
  if (service === "rds") params.set("engine", engine);
  return api<AwsOptionsResponse>(`/calculator/aws/options?${params.toString()}`, { signal });
}
export function fetchOciOptions(service: "compute", region: string, signal?: AbortSignal): Promise<OciComputeOptions>;
export function fetchOciOptions(service: "db_system", region: string, signal?: AbortSignal): Promise<OciDbOptions>;
export function fetchOciOptions(service: "compute" | "db_system", region: string, signal?: AbortSignal) {
  return api<OciComputeOptions | OciDbOptions>(
    `/calculator/oci/options?service=${service}&region=${encodeURIComponent(region)}`, { signal },
  );
}
export function estimateCalculator(request: CalculatorRequest, signal?: AbortSignal) {
  return api<CalculatorEstimate>("/calculator/estimate", {
    method: "POST",
    body: JSON.stringify(request),
    signal,
  });
}

/** A display-only identifier; never use this on outgoing API requests. */
export function compactIdentifier(value: string, limit = 36) {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

export function positiveNumber(value: string, max = Number.MAX_SAFE_INTEGER): boolean {
  const normalized = value.replace(",", ".").trim();
  if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(normalized)) return false;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) && parsed > 0 && parsed <= max;
}
export function decimalValue(value: string) {
  return value.replace(",", ".").trim();
}
export function nonNegativePercent(value: string, max: number) {
  const normalized = decimalValue(value);
  if (!/^(?:\d+(?:\.\d+)?|\.\d+)$/.test(normalized)) return false;
  if ((normalized.split(".")[1]?.length ?? 0) > 6) return false;
  const percent = Number(normalized);
  return Number.isFinite(percent) && percent >= 0 && percent <= max;
}
