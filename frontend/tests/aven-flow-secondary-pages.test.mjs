import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Flow composes the official Aven operational stack", async () => {
  const page = await source("../app/flow/page.tsx");

  for (const component of [
    "PageHeader",
    "Section",
    "FilterBar",
    "MetricCard",
    "ChartCard",
    "DataState",
    "CurrencyDisplay",
    "ProviderBadge",
    "StatusIndicator",
    "Table",
    "Dialog",
    "Pagination",
  ]) {
    assert.ok(page.includes(component), `expected ${component} in Flow`);
  }

  assert.ok(!page.includes('@/components/page-header'));
  assert.ok(!page.includes('className="button'));
  assert.ok(!page.includes('className="panel'));
  assert.ok(!page.includes("useTheme("));
  assert.ok(!page.includes("resolvedTheme"));
});

test("Flow preserves the existing query and mutation contracts", async () => {
  const page = await source("../app/flow/page.tsx");

  for (const contract of [
    'api<CloudAccount[]>("/cloud-accounts")',
    'api<FlowOptions>(`/finops/flow/options?${optionQuery}`)',
    'api<SummaryItem[]>(`/finops/flow/summary?${base}`)',
    'api<TimeseriesResponse>(`/finops/flow/timeseries?${chart}`)',
    'api<Breakdowns>(`/finops/flow/breakdowns?${base}`)',
    'api<FlowEntryPage>(`/finops/flow/entries?${tableQuery}`)',
    'api<FlowEntry>("/finops/ledger/manual"',
    'api<FlowEntry>(`/finops/ledger/${reverseTarget.id}/reverse`',
  ]) {
    assert.ok(page.includes(contract), `missing preserved contract: ${contract}`);
  }

  assert.ok(page.includes("manual_entry_request_id"));
  assert.ok(page.includes("setReloadToken((value) => value + 1)"));
  assert.ok(page.includes("setReverseTarget(entry)"));
  assert.ok(page.includes("opportunity_id"));
});

test("Flow keeps existing filters and does not invent cross-currency totals", async () => {
  const page = await source("../app/flow/page.tsx");

  for (const state of ["period", "provider", "accountId", "currency", "source", "periodicity", "entryType", "search", "page"]) {
    assert.ok(page.includes(state), `expected existing Flow filter/state ${state}`);
  }
  assert.ok(page.includes("Todas (sem consolidar)"));
  assert.ok(page.includes("Cada moeda e base financeira permanece separada"));
  assert.ok(!page.includes("Flow Health Score"));
  assert.ok(!page.includes("Operational Efficiency"));
});

test("Flow page keeps Application Shell scroll ownership", async () => {
  const css = await source("../app/flow/flow-layout.module.css");

  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.match(css, /\.chartScroll[\s\S]*overflow-x:\s*auto/);
});

test("Collections preserve real collection, comparison and manual-run contracts", async () => {
  const workspace = await source("../components/collection-workspace.tsx");
  const launcher = await source("../components/manual-collection-launcher.tsx");
  const compare = await source("../app/collections/[collectionId]/compare/page.tsx");
  const layout = await source("../app/collections/layout.tsx");

  for (const contract of [
    'path: `/collections?${query}`',
    'path: `/collections/${encodeURIComponent(collectionId || "")}`',
    'path: `/collections/options?${optionQuery}`',
  ]) {
    assert.ok(workspace.includes(contract), `missing Collections contract: ${contract}`);
  }
  assert.ok(workspace.includes("window.setInterval"));
  assert.ok(workspace.includes("15000"));
  assert.ok(launcher.includes('api<CloudAccount[]>("/cloud-accounts")'));
  assert.ok(launcher.includes('api<ProviderCapabilities[]>("/cloud-accounts/capabilities")'));
  assert.ok(launcher.includes('api<CurrentUser>("/auth/me")'));
  assert.ok(launcher.includes('`/cloud-accounts/${selected.id}/scans`'));
  assert.ok(launcher.includes("canRunCloudAnalysis(role)"));
  assert.ok(launcher.includes("<Dialog"));
  assert.ok(launcher.includes("<Select"));
  assert.ok(compare.includes('path: `/collections/${collectionId}/compare?${comparisonQuery}`'));
  assert.ok(compare.includes('path: `/collections/${collectionId}/comparison-options?limit=100`'));
  assert.ok(layout.includes("collections-layout.module.css"));
});

test("Scans preserve the existing APIs, links and polling while using Aven", async () => {
  const page = await source("../app/scans/page.tsx");

  for (const contract of [
    'api<Scan[]>("/scans?limit=100")',
    'api<AwsAccount[]>("/accounts")',
    'api<CollectionRun[]>("/collections?limit=200")',
    "window.setInterval(load, 10000)",
    "window.clearInterval(timer)",
    "PageHeader",
    "DataState",
    "StatusIndicator",
    "Table",
  ]) {
    assert.ok(page.includes(contract), `missing Scans contract: ${contract}`);
  }
  assert.ok(page.includes('href={`/collections/${run.id}`}'));
  assert.ok(page.includes('href={`/collections/${run.id}/compare`}'));
  assert.ok(!page.includes("StatusBadge"));
  assert.ok(!page.includes('@/components/page-header'));
});

test("Legacy aliases remain redirects instead of becoming duplicate pages", async () => {
  const ledger = await source("../app/finops/ledger/page.tsx");
  const security = await source("../app/security/page.tsx");

  assert.ok(ledger.includes('redirect("/flow")'));
  assert.ok(security.includes('redirect("/settings/security")'));
  assert.ok(!ledger.includes("PageHeader"));
  assert.ok(!security.includes("PageHeader"));
});

test("Task 24.16 migrated files pass the Aven hardcode gate independently", async () => {
  const filenames = [
    "app/flow/page.tsx",
    "app/flow/flow-layout.module.css",
    "app/scans/page.tsx",
    "app/scans/scans.module.css",
    "app/collections/collection.module.css",
    "app/collections/collections-layout.module.css",
    "app/collections/layout.tsx",
    "components/page-header.tsx",
    "components/manual-collection-launcher.tsx",
    "components/manual-collection-launcher.module.css",
  ];

  const entries = await Promise.all(
    filenames.map(async (filename) => [filename, await source(`../${filename}`)]),
  );
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));

  assert.deepEqual(summarize(violations), {
    colors: 0,
    spacing: 0,
    radius: 0,
    typography: 0,
  });
  assert.deepEqual(violations, []);
});

test("Task 24.16 documentation records scope, tests and readiness gates", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_FLOW_AND_SECONDARY_PAGES.md", import.meta.url), "utf8");

  for (const section of [
    "## Functional Foundation Gate",
    "## Route Inventory",
    "## FinOps Flow Architecture",
    "## Existing Flow Actions",
    "## Test Baseline",
    "## Test Isolation Rules",
    "## Legacy Migration",
    "MIGRATED:",
    "KEPT AS-IS:",
    "OUT OF SCOPE — FUNCTIONALITY DOES NOT EXIST:",
    "DEPRECATED / REVIEW LATER:",
  ]) {
    assert.ok(docs.includes(section), `missing documentation section ${section}`);
  }

  assert.ok(docs.includes("Test configuration changes: None"));
  assert.ok(docs.includes("Environment variable changes: None"));
  assert.ok(docs.includes("Were any new features created to complete the Aven navigation? NO"));
  assert.ok(docs.includes("Is Task 24.17 ready to start? YES"));
});
