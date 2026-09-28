"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
} from "react";
import { api } from "@/lib/api";
import {
  serializeQueryKey,
  sharedQueryCache,
} from "@/lib/query-cache.mjs";
import type { QueryKey } from "@/lib/query-keys.mjs";

type QueryOptions<T> = {
  key: QueryKey;
  path: string;
  enabled?: boolean;
  staleTime?: number;
  gcTime?: number;
  keepPreviousData?: boolean;
  placeholderIdentity?: string;
};

type PreviousValue<T> = {
  identity: string;
  data: T;
};

export function useApiQuery<T>({
  key,
  path,
  enabled = true,
  staleTime = 0,
  gcTime = 5 * 60_000,
  keepPreviousData = false,
  placeholderIdentity = "",
}: QueryOptions<T>) {
  const [, render] = useReducer((value) => value + 1, 0);
  const keyId = useMemo(() => serializeQueryKey(key), [key]);
  const stableKey = useMemo(() => key, [keyId]);
  const previous = useRef<PreviousValue<T> | null>(null);
  const snapshot = sharedQueryCache.snapshot<T>(stableKey);

  useEffect(
    () => sharedQueryCache.subscribe(stableKey, render),
    [keyId, stableKey],
  );

  const execute = useCallback(
    (force = false) =>
      sharedQueryCache.fetch<T>({
        key: stableKey,
        staleTime,
        gcTime,
        force,
        queryFn: () => api<T>(path),
      }),
    [gcTime, keyId, path, stableKey, staleTime],
  );

  useEffect(() => {
    if (!enabled) return;
    void execute(false).catch(() => undefined);
  }, [enabled, execute, snapshot.invalidationVersion]);

  if (snapshot.hasData) {
    previous.current = {
      identity: placeholderIdentity,
      data: snapshot.data as T,
    };
  }

  const placeholder =
    !snapshot.hasData &&
    keepPreviousData &&
    previous.current?.identity === placeholderIdentity
      ? previous.current.data
      : undefined;
  const data = snapshot.hasData ? (snapshot.data as T) : placeholder;
  const isPlaceholderData = !snapshot.hasData && placeholder !== undefined;
  const isLoading =
    enabled &&
    data === undefined &&
    !snapshot.error &&
    !snapshot.hasData;
  const isStale =
    !snapshot.hasData ||
    snapshot.updatedAt === 0 ||
    Date.now() - snapshot.updatedAt >= staleTime;

  const refetch = useCallback(() => execute(true), [execute]);

  return {
    data,
    error: snapshot.error,
    isLoading,
    isFetching: snapshot.isFetching,
    isPlaceholderData,
    isStale,
    updatedAt: snapshot.updatedAt,
    refetch,
  };
}

export function prefetchApiQuery<T = unknown>({
  key,
  path,
  staleTime = 0,
  gcTime = 5 * 60_000,
}: Omit<QueryOptions<T>, "enabled" | "keepPreviousData" | "placeholderIdentity">) {
  return sharedQueryCache.fetch<T>({
    key,
    staleTime,
    gcTime,
    queryFn: () => api<T>(path),
  });
}

export function invalidateApiQueries(prefix: QueryKey) {
  return sharedQueryCache.invalidate(prefix);
}

export function clearApiQueryCache() {
  sharedQueryCache.clear();
}
