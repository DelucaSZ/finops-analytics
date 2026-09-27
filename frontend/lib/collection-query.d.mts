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
export const COLLECTION_STATUSES: Record<string, string>;
export const COLLECTION_SORTS: string[];
export function parseCollectionQuery(value: string): CollectionQuery;
export function buildCollectionQuery(state: CollectionQuery): string;
export function patchCollectionQuery(
  current: string,
  patch: Record<string, string | number>,
): string;
export function collectionOpportunitiesUrl(id: string): string;
export function localDateTime(value: string): string;
export function durationLabel(
  run: { duration_seconds: number | null; status: string; started_at: string },
  now?: number,
): string;
