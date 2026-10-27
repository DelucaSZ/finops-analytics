import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const componentSource = readFileSync(
  new URL("../components/dashboard-operational-insights.tsx", import.meta.url),
  "utf8",
);
const dashboardSource = readFileSync(
  new URL("../components/executive-dashboard.tsx", import.meta.url),
  "utf8",
);
const serverStateSource = readFileSync(
  new URL("../lib/server-state.ts", import.meta.url),
  "utf8",
);
const queryKeysSource = readFileSync(
  new URL("../lib/query-keys.mjs", import.meta.url),
  "utf8",
);
const styleSource = readFileSync(
  new URL("../components/dashboard-operational-insights.module.css", import.meta.url),
  "utf8",
);

test("dashboard uses the dedicated conditional operational-insights endpoint", () => {
  assert.match(dashboardSource, /CollectionFailureOperationalInsights/);
  assert.match(componentSource, /\/dashboard\/operational-insights/);
  assert.match(componentSource, /queryKeys\.dashboard\.operationalInsights/);
  assert.match(queryKeysSource, /"operational-insights"/);
  assert.doesNotMatch(componentSource, /\/dashboard\/collection-health/);
});

test("healthy loading and endpoint-error states do not render a permanent card", () => {
  assert.match(
    componentSource,
    /request\.isLoading \|\| request\.error \|\| !failures\?\.count\) return null/,
  );
  assert.doesNotMatch(componentSource, /Saúde das coletas/);
  assert.doesNotMatch(componentSource, /freshness/i);
});

test("multiple failures are expandable and every item deep-links to its failed run", () => {
  assert.match(componentSource, /<details className=\{styles\.details\}>/);
  assert.match(componentSource, /<summary>/);
  assert.match(
    componentSource,
    /\/collections\/\$\{encodeURIComponent\(item\.collection_run_id\)\}/,
  );
  assert.match(componentSource, /status: "FAILED"/);
  assert.match(componentSource, /Nova coleta em andamento desde/);
  assert.match(componentSource, /failures\.truncated/);
});

test("insight revalidates independently without accelerating the executive summary", () => {
  assert.match(componentSource, /INSIGHT_REFRESH_INTERVAL = 45_000/);
  assert.match(componentSource, /\.\.\.cachePolicy\.insight/);
  assert.match(queryKeysSource, /insight: \{ staleTime: 15_000, gcTime: 2 \* 60_000 \}/);
  assert.match(serverStateSource, /refetchInterval\?: number/);
  assert.match(serverStateSource, /document\.visibilityState !== "visible"/);
});

test("operational insight uses Aven semantic components and tokenized responsive flow", () => {
  assert.match(componentSource, /<Section/);
  assert.match(componentSource, /aria-label="Atenção operacional"/);
  assert.match(componentSource, /<Alert[\s\S]*variant="warning"/);
  assert.match(componentSource, /<StatusIndicator status="danger" label="Falha"/);
  assert.match(componentSource, /<ProviderBadge provider=\{item\.provider\}/);
  assert.match(styleSource, /display: flex/);
  assert.match(styleSource, /flex-wrap: wrap/);
  assert.match(styleSource, /gap: var\(--space-2\)/);
  assert.doesNotMatch(styleSource, /#[0-9a-f]{3,8}/i);
});
