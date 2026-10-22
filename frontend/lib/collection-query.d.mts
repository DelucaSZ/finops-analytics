export type CollectionQuery = {
  provider: string;
  account_id: string;
  status: string;
  date_from: string;
  date_to: string;
  analyzer_version: string;
  page: number;
  page_size: number;
  sort: string;
  order: string;
};
export type CollectionDiscoveryType =
  | "observed"
  | "first_seen"
  | "new_vs_previous"
  | "reappeared"
  | "continued"
  | "no_longer_detected";
export type CollectionDiscoveryLinkOptions = {
  provider?: string;
  accountId?: string;
};
export const COLLECTION_STATUSES: Record<string, string>;
export const COLLECTION_SORTS: string[];
export const COLLECTION_DISCOVERY_TYPES: CollectionDiscoveryType[];
export const COLLECTION_DISCOVERY_LABELS: Record<CollectionDiscoveryType, string>;
export function parseCollectionQuery(value: string): CollectionQuery;
export function buildCollectionQuery(state: CollectionQuery): string;
export function patchCollectionQuery(
  current: string,
  patch: Record<string, string | number>,
): string;
export function buildObservedOpportunitiesHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function buildFirstSeenOpportunitiesHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function buildNewVsPreviousHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function buildReappearedHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function buildContinuedHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function buildNoLongerDetectedHref(id: string, options?: CollectionDiscoveryLinkOptions): string;
export function collectionOpportunitiesUrl(id: string): string;
export function localDateTime(value: string): string;
export function durationLabel(
  run: { duration_seconds: number | null; status: string; started_at: string },
  now?: number,
): string;
