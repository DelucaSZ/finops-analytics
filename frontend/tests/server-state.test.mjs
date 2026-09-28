import assert from "node:assert/strict";
import test from "node:test";
import {
  QueryCache,
  queryKeyStartsWith,
  serializeQueryKey,
} from "../lib/query-cache.mjs";
import { queryKeys } from "../lib/query-keys.mjs";

test("query key serialization is deterministic for object keys", () => {
  assert.equal(
    serializeQueryKey(["scope", { provider: "aws", account_id: "A" }]),
    serializeQueryKey(["scope", { account_id: "A", provider: "aws" }]),
  );
});

test("provider and account are isolated in opportunity option keys", () => {
  const awsA = serializeQueryKey(queryKeys.opportunities.options("aws", "A"));
  const awsB = serializeQueryKey(queryKeys.opportunities.options("aws", "B"));
  const ociA = serializeQueryKey(queryKeys.opportunities.options("oci", "A"));
  assert.notEqual(awsA, awsB);
  assert.notEqual(awsA, ociA);
});

test("comparison identity includes baseline, category and page", () => {
  const first = serializeQueryKey(
    queryKeys.collections.comparison("target", "base-a", "NEW", 1, 50),
  );
  const nextPage = serializeQueryKey(
    queryKeys.collections.comparison("target", "base-a", "NEW", 2, 50),
  );
  const otherBaseline = serializeQueryKey(
    queryKeys.collections.comparison("target", "base-b", "NEW", 1, 50),
  );
  assert.notEqual(first, nextPage);
  assert.notEqual(first, otherBaseline);
});

test("prefix invalidation matches only related queries", () => {
  assert.equal(
    queryKeyStartsWith(
      queryKeys.opportunities.detail("123"),
      queryKeys.opportunities.all,
    ),
    true,
  );
  assert.equal(
    queryKeyStartsWith(
      queryKeys.collections.detail("123"),
      queryKeys.opportunities.all,
    ),
    false,
  );
});

test("simultaneous requests for the same key are deduplicated", async () => {
  let calls = 0;
  const cache = new QueryCache();
  const key = queryKeys.dashboard.summary("aws", "A");
  const queryFn = async () => {
    calls += 1;
    await Promise.resolve();
    return { value: calls };
  };

  const [first, second] = await Promise.all([
    cache.fetch({ key, queryFn, staleTime: 60_000 }),
    cache.fetch({ key, queryFn, staleTime: 60_000 }),
  ]);

  assert.equal(calls, 1);
  assert.deepEqual(first, second);
});

test("fresh data is reused until invalidated", async () => {
  let now = 1_000;
  let calls = 0;
  const cache = new QueryCache(() => now);
  const key = queryKeys.opportunities.list("provider=aws&account_id=A");
  const queryFn = async () => ++calls;

  assert.equal(
    await cache.fetch({ key, queryFn, staleTime: 60_000 }),
    1,
  );
  now += 30_000;
  assert.equal(
    await cache.fetch({ key, queryFn, staleTime: 60_000 }),
    1,
  );
  assert.equal(calls, 1);

  cache.invalidate(queryKeys.opportunities.all);
  assert.equal(
    await cache.fetch({ key, queryFn, staleTime: 60_000 }),
    2,
  );
  assert.equal(calls, 2);
});

test("clear removes private cached data", async () => {
  const cache = new QueryCache();
  const key = queryKeys.collections.detail("run-1");
  await cache.fetch({
    key,
    queryFn: async () => ({ id: "run-1" }),
    staleTime: 60_000,
  });
  assert.equal(cache.snapshot(key).hasData, true);
  cache.clear();
  assert.equal(cache.snapshot(key).hasData, false);
});
