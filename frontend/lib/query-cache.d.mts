import type { QueryKey } from "./query-keys.mjs";

export type QuerySnapshot<T = unknown> = {
  data: T | undefined;
  hasData: boolean;
  error: Error | null;
  updatedAt: number;
  isFetching: boolean;
  invalidationVersion: number;
};

export type QueryFetchOptions<T> = {
  key: QueryKey;
  queryFn: () => Promise<T>;
  staleTime?: number;
  gcTime?: number;
  force?: boolean;
};

export class QueryCache {
  constructor(now?: () => number);
  snapshot<T = unknown>(key: QueryKey): QuerySnapshot<T>;
  subscribe(key: QueryKey, listener: () => void): () => void;
  fetch<T>(options: QueryFetchOptions<T>): Promise<T>;
  invalidate(prefix: QueryKey): number;
  clear(): void;
  prune(): void;
}

export function serializeQueryKey(key: QueryKey): string;
export function queryKeyStartsWith(key: QueryKey, prefix: QueryKey): boolean;
export const sharedQueryCache: QueryCache;
