import test from "node:test";
import assert from "node:assert/strict";
import {
  buildCollectionQuery,
  collectionOpportunitiesUrl,
  durationLabel,
  localDateTime,
  parseCollectionQuery,
  patchCollectionQuery,
} from "../lib/collection-query.mjs";

test("collection filters and pagination survive a URL round trip", () => {
  const state = parseCollectionQuery(
    "provider=oci&account_id=ocid1.tenancy.a&status=FAILED&date_from=2026-09-01T00%3A00%3A00Z&date_to=2026-10-01T00%3A00%3A00Z&analyzer_version=v1&page=3&page_size=25&sort=opportunities_found&order=asc",
  );
  assert.equal(state.account_id, "ocid1.tenancy.a");
  assert.equal(state.page, 3);
  assert.deepEqual(parseCollectionQuery(buildCollectionQuery(state)), state);
});
test("filter or sorting changes reset pagination; explicit page preserves filters", () => {
  assert.equal(
    parseCollectionQuery(
      patchCollectionQuery("page=8&provider=aws", { status: "FAILED" }),
    ).page,
    1,
  );
  const state = parseCollectionQuery(
    patchCollectionQuery("status=FAILED&provider=oci", { page: 3 }),
  );
  assert.equal(state.page, 3);
  assert.equal(state.status, "FAILED");
  assert.equal(state.provider, "oci");
});
test("invalid sorting pagination and status fall back safely", () => {
  const state = parseCollectionQuery(
    "page=-5&page_size=999&sort=secret&status=STUCK",
  );
  assert.equal(state.page, 1);
  assert.equal(state.page_size, 50);
  assert.equal(state.sort, "started_at");
  assert.equal(state.status, "");
});
test("related opportunities preserve the exact collection ID", () => {
  const url = new URL(collectionOpportunitiesUrl("a/b & c"), "http://test");
  assert.equal(url.pathname, "/opportunities");
  assert.equal(url.searchParams.get("collection_run_id"), "a/b & c");
});
test("duration is derived without invented progress", () => {
  assert.equal(
    durationLabel({
      status: "SUCCESS",
      duration_seconds: 134,
      started_at: "2026-09-25T12:00:00Z",
    }),
    "2m 14s",
  );
  assert.equal(
    durationLabel(
      {
        status: "RUNNING",
        duration_seconds: null,
        started_at: "2026-09-25T12:00:00Z",
      },
      Date.parse("2026-09-25T12:01:00Z"),
    ),
    "Em andamento há 1m 0s",
  );
  assert.equal(
    durationLabel({
      status: "FAILED",
      duration_seconds: null,
      started_at: "2026-09-25T12:00:00Z",
    }),
    "—",
  );
  assert.equal(localDateTime("invalid"), "");
});
