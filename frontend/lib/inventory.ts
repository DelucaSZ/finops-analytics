export type InventorySortField =
  | "name"
  | "provider"
  | "account"
  | "resource_type"
  | "service"
  | "region"
  | "lifecycle_status"
  | "presence_status"
  | "first_seen_at"
  | "last_seen_at";

export type InventorySortDirection = "asc" | "desc";

export interface InventoryResource {
  id: number;
  provider: string;
  cloud_account_id: number;
  native_account_id: string;
  account_name: string | null;
  resource_id: string;
  resource_type: string;
  native_resource_type: string | null;
  service: string | null;
  name: string | null;
  region: string | null;
  availability_zone: string | null;
  lifecycle_status: string;
  native_status: string | null;
  presence_status: string;
  tags: Record<string, unknown>;
  attributes: Record<string, unknown>;
  first_seen_at: string;
  last_seen_at: string;
  last_seen_collection_run_id: string | null;
}

export interface InventoryPage {
  items: InventoryResource[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface InventoryAccountOption {
  id: number;
  name: string;
  native_account_id: string;
  provider: string;
}

export interface InventoryOptions {
  providers: string[];
  accounts: InventoryAccountOption[];
  regions: string[];
  resource_types: string[];
  services: string[];
  lifecycle_statuses: string[];
  presence_statuses: string[];
}
