function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .map((key) => [key, stableValue(value[key])]),
    );
  }
  return value;
}

export function serializeQueryKey(key) {
  return JSON.stringify(stableValue(key));
}

export function queryKeyStartsWith(key, prefix) {
  if (!Array.isArray(key) || !Array.isArray(prefix) || prefix.length > key.length) {
    return false;
  }
  return prefix.every(
    (value, index) =>
      serializeQueryKey([value]) === serializeQueryKey([key[index]]),
  );
}

function emptySnapshot() {
  return {
    data: undefined,
    hasData: false,
    error: null,
    updatedAt: 0,
    isFetching: false,
    invalidationVersion: 0,
  };
}

export class QueryCache {
  constructor(now = () => Date.now()) {
    this.now = now;
    this.entries = new Map();
    this.listeners = new Map();
  }

  ensure(key, gcTime = 5 * 60_000) {
    const id = serializeQueryKey(key);
    let entry = this.entries.get(id);
    if (!entry) {
      entry = {
        key,
        data: undefined,
        hasData: false,
        error: null,
        updatedAt: 0,
        isFetching: false,
        invalidationVersion: 0,
        promise: null,
        gcTime,
        lastAccessedAt: this.now(),
      };
      this.entries.set(id, entry);
    } else {
      entry.key = key;
      entry.gcTime = Math.max(entry.gcTime || 0, gcTime);
      entry.lastAccessedAt = this.now();
    }
    return entry;
  }

  snapshot(key) {
    const entry = this.entries.get(serializeQueryKey(key));
    if (!entry) return emptySnapshot();
    entry.lastAccessedAt = this.now();
    return {
      data: entry.data,
      hasData: entry.hasData,
      error: entry.error,
      updatedAt: entry.updatedAt,
      isFetching: entry.isFetching,
      invalidationVersion: entry.invalidationVersion,
    };
  }

  subscribe(key, listener) {
    const id = serializeQueryKey(key);
    const listeners = this.listeners.get(id) || new Set();
    listeners.add(listener);
    this.listeners.set(id, listeners);
    return () => {
      listeners.delete(listener);
      if (!listeners.size) this.listeners.delete(id);
    };
  }

  emit(key) {
    const listeners = this.listeners.get(serializeQueryKey(key));
    if (!listeners) return;
    for (const listener of listeners) listener();
  }

  async fetch({
    key,
    queryFn,
    staleTime = 0,
    gcTime = 5 * 60_000,
    force = false,
  }) {
    this.prune();
    const entry = this.ensure(key, gcTime);
    const fresh =
      entry.hasData &&
      entry.updatedAt > 0 &&
      this.now() - entry.updatedAt < staleTime;
    if (!force && fresh) return entry.data;
    if (entry.promise) return entry.promise;

    entry.isFetching = true;
    entry.error = null;
    this.emit(key);

    const promise = Promise.resolve()
      .then(queryFn)
      .then((data) => {
        entry.data = data;
        entry.hasData = true;
        entry.error = null;
        entry.updatedAt = this.now();
        entry.lastAccessedAt = this.now();
        return data;
      })
      .catch((error) => {
        entry.error = error instanceof Error ? error : new Error(String(error));
        entry.lastAccessedAt = this.now();
        throw error;
      })
      .finally(() => {
        entry.promise = null;
        entry.isFetching = false;
        this.emit(key);
      });

    entry.promise = promise;
    return promise;
  }

  invalidate(prefix) {
    let count = 0;
    for (const entry of this.entries.values()) {
      if (!queryKeyStartsWith(entry.key, prefix)) continue;
      entry.updatedAt = 0;
      entry.invalidationVersion += 1;
      count += 1;
      this.emit(entry.key);
    }
    return count;
  }

  clear() {
    const keys = [...this.entries.values()].map((entry) => entry.key);
    this.entries.clear();
    for (const key of keys) this.emit(key);
  }

  prune() {
    const now = this.now();
    for (const [id, entry] of this.entries.entries()) {
      if (entry.promise || this.listeners.has(id)) continue;
      if (now - entry.lastAccessedAt > entry.gcTime) this.entries.delete(id);
    }
  }
}

export const sharedQueryCache = new QueryCache();
