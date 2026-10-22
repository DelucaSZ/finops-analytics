import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
} from "../lib/opportunity-query.mjs";

const dashboardSource = readFileSync(
  new URL("../components/executive-dashboard.tsx", import.meta.url),
  "utf8",
);

test("dashboard comparison URL defaults to all actionable statuses and preserves frozen context", () => {
  const state = parseOpportunitySearchParams(
    "provider=aws&comparison_context=v1.payload.signature&comparison_kind=new_vs_previous&discovery_type=new_vs_previous",
  );

  assert.equal(state.status, "");
  assert.equal(state.comparisonContext, "v1.payload.signature");
  assert.equal(state.comparisonKind, "new_vs_previous");
  assert.equal(state.discoveryType, "new_vs_previous");

  const list = new URLSearchParams(buildOpportunityApiQuery(state));
  const stats = new URLSearchParams(buildOpportunityStatsQuery(state));
  assert.equal(list.get("comparison_context"), "v1.payload.signature");
  assert.equal(list.get("comparison_kind"), "new_vs_previous");
  assert.equal(list.get("discovery_type"), "new_vs_previous");
  assert.equal(list.get("provider"), "aws");
  assert.equal(list.has("status"), false);
  assert.equal(stats.get("comparison_context"), "v1.payload.signature");
  assert.equal(stats.get("comparison_kind"), "new_vs_previous");
});

test("additional opportunity filters stay inside the dashboard comparison context", () => {
  const state = parseOpportunitySearchParams(
    "comparison_context=v1.payload.signature&comparison_kind=new_vs_previous&discovery_type=new_vs_previous&severity=high&search=i-123&page=3&sort=estimated_savings&order=asc",
  );
  const query = new URLSearchParams(buildOpportunityApiQuery(state));

  assert.equal(query.get("comparison_context"), "v1.payload.signature");
  assert.equal(query.get("severity"), "high");
  assert.equal(query.get("search"), "i-123");
  assert.equal(query.get("page"), "3");
  assert.equal(query.get("sort"), "estimated_savings");
  assert.equal(query.get("order"), "asc");
});

test("clearing comparison discovery removes its frozen context without dropping unrelated filters", () => {
  const next = patchOpportunityUrl(
    "provider=oci&comparison_context=v1.payload.signature&comparison_kind=reappeared&discovery_type=reappeared&severity=medium&page=4",
    { discovery_type: null },
  );

  assert.equal(next.get("provider"), "oci");
  assert.equal(next.get("severity"), "medium");
  assert.equal(next.has("comparison_context"), false);
  assert.equal(next.has("comparison_kind"), false);
  assert.equal(next.has("discovery_type"), false);
  assert.equal(next.get("page"), "1");
});

test("dashboard KPI uses Opportunities with a frozen context and never links to Collections", () => {
  assert.match(dashboardSource, /Novas desde a coleta anterior/);
  assert.match(dashboardSource, /comparison_context/);
  assert.match(dashboardSource, /comparison_kind/);
  assert.match(dashboardSource, /first_seen_count/);
  assert.match(dashboardSource, /reappeared_count/);
  assert.match(dashboardSource, /identified_preset:\s*"last_24h"/);
  assert.doesNotMatch(dashboardSource, /href=.*\/collections/);
  assert.doesNotMatch(dashboardSource, /navegação será refinada na 24\.12/);
});
