import test from "node:test";
import assert from "node:assert/strict";
import {
  buildDashboardNewOpportunitiesHref,
  buildDashboardRecentOpportunitiesHref,
} from "../lib/dashboard-query.mjs";
import {
  buildOpportunityApiQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
} from "../lib/opportunity-query.mjs";

const scope = { provider: "aws", accountId: "111111111111" };

test("new-since-previous deep link opens exact opportunity comparison, never collections", () => {
  const href = buildDashboardNewOpportunitiesHref(scope, "signed-context", "new_vs_previous");
  assert.ok(href);
  const url = new URL(href, "http://deepops.local");
  assert.equal(url.pathname, "/opportunities");
  assert.equal(url.searchParams.get("provider"), "aws");
  assert.equal(url.searchParams.get("account_id"), "111111111111");
  assert.equal(url.searchParams.get("discovery_type"), "new_vs_previous");
  assert.equal(url.searchParams.get("comparison_context"), "signed-context");
  assert.equal(url.searchParams.get("status"), "all");
  assert.doesNotMatch(href, /\/collections/);
});

test("comparison context preserves all actionable statuses and reaches API", () => {
  const state = parseOpportunitySearchParams(
    "provider=aws&status=all&discovery_type=new_vs_previous&comparison_context=signed-context",
  );
  assert.equal(state.status, "");
  assert.equal(state.current, false);
  assert.equal(state.comparisonContext, "signed-context");
  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(query.get("comparison_context"), "signed-context");
  assert.equal(query.get("discovery_type"), "new_vs_previous");
  assert.equal(query.has("current"), false);
  assert.equal(query.has("status"), false);
});

test("clearing comparison filter clears its frozen context", () => {
  const params = patchOpportunityUrl(
    "discovery_type=new_vs_previous&comparison_context=signed-context&page=3",
    { discovery_type: null },
  );
  assert.equal(params.has("discovery_type"), false);
  assert.equal(params.has("comparison_context"), false);
  assert.equal(params.get("page"), "1");
});

test("last-24h shortcut is temporal first-seen discovery and preserves scope", () => {
  const href = buildDashboardRecentOpportunitiesHref(scope);
  const url = new URL(href, "http://deepops.local");
  assert.equal(url.pathname, "/opportunities");
  assert.equal(url.searchParams.get("provider"), "aws");
  assert.equal(url.searchParams.get("account_id"), "111111111111");
  assert.equal(url.searchParams.get("date_field"), "first_seen");
  assert.equal(url.searchParams.get("identified_preset"), "last_24h");
  assert.equal(url.searchParams.has("comparison_context"), false);
});
