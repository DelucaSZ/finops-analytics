import type { OpportunityQueryState } from "./opportunity-query.mjs";

export type OpportunityArchiveFilters = Partial<{
  provider: string;
  account_id: string;
  region: string;
  service: string;
  resource_type: string;
  status: string;
  presence_status: string;
  severity: string;
  rule: string;
  collection_run_id: string;
  resource_id: string;
  search: string;
  current: boolean;
}>;

export type ArchiveScope = {
  filters: OpportunityArchiveFilters;
  archive_all: boolean;
};

export function buildArchiveFilters(state: OpportunityQueryState): OpportunityArchiveFilters;
export function buildArchiveScope(
  state: OpportunityQueryState,
  options?: { archiveAll?: boolean },
): ArchiveScope;
export function archiveResultMessage(result: { archived?: number; already_archived?: number }): string;
export function periodCloseResultMessage(
  result: { snapshots_created?: number; archived?: number },
  label: string,
): string;
