import test from "node:test";
import assert from "node:assert/strict";

import {
  buildContinuedHref,
  buildFirstSeenOpportunitiesHref,
  buildNewVsPreviousHref,
  buildNoLongerDetectedHref,
  buildObservedOpportunitiesHref,
  buildReappearedHref,
} from "../lib/collection-query.mjs";

const runId = "11111111-2222-3333-4444-555555555555";
const scope = { provider: "aws", accountId: "123456789012" };

const cases = [
  [buildObservedOpportunitiesHref, "observed"],
  [buildFirstSeenOpportunitiesHref, "first_seen"],
  [buildNewVsPreviousHref, "new_vs_previous"],
  [buildReappearedHref, "reappeared"],
  [buildContinuedHref, "continued"],
  [buildNoLongerDetectedHref, "no_longer_detected"],
];

test("collection investigation helpers centralize exact discovery links", () => {
  for (const [build, discoveryType] of cases) {
    const url = new URL(build(runId, scope), "https://deepops.local");
    assert.equal(url.pathname, `/opportunities/collection/${runId}`);
    assert.equal(url.searchParams.get("discovery_type"), discoveryType);
    assert.equal(url.searchParams.get("provider"), "aws");
    assert.equal(url.searchParams.get("account_id"), "123456789012");
    assert.equal(url.searchParams.get("page"), "1");
    assert.equal(url.searchParams.has("status"), false);
  }
});

test("first_seen link carries the historical first-seen run identity", () => {
  const url = new URL(buildFirstSeenOpportunitiesHref(runId), "https://deepops.local");
  assert.equal(url.searchParams.get("first_seen_collection_run_id"), runId);
});
