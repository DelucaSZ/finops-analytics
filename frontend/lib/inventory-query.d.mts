import type { InventorySortDirection, InventorySortField } from "./inventory";

export type InventoryPresenceFilter = "active" | "missing" | "all";

export interface InventoryQueryState {
  provider: string;
  account: string;
  region: string;
  resourceType: string;
  lifecycleStatus: string;
  presenceStatus: InventoryPresenceFilter;
  service: string;
  search: string;
  sort: InventorySortField;
  direction: InventorySortDirection;
  page: number;
  pageSize: number;
}

export const defaultInventoryQueryState: Readonly<InventoryQueryState>;

export function parseInventorySearchParams(params: Pick<URLSearchParams, "get">): InventoryQueryState;
export function buildInventoryApiQuery(state: InventoryQueryState): string;
export function buildInventoryOptionsQuery(state: InventoryQueryState): string;
export function buildInventoryUrlSearch(state: InventoryQueryState): string;
export function patchInventoryUrl(state: InventoryQueryState, changes: Partial<InventoryQueryState>): string;
