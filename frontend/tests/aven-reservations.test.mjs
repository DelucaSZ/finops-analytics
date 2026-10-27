import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Reservations composes the official Aven operational stack", async () => {
  const page = await source("../app/rds/reservations/page.tsx");
  for (const component of [
    "PageHeader", "Section", "FilterBar", "AccountSelector", "MetricCard",
    "PercentageDisplay", "ProviderBadge", "ResourceIdentifier", "StatusIndicator",
    "DataState", "ChartCard", "Table", "Pagination", "Alert", "Skeleton", "Tabs",
  ]) assert.ok(page.includes(component), `expected ${component} in Reservations`);
  assert.ok(!page.includes('@/components/page-header'));
  assert.ok(!page.includes("function MetricCard"));
  assert.ok(!page.includes("function Badge"));
});

test("Reservations preserves lazy endpoint fetching and keeps theme outside query signatures", async () => {
  const page = await source("../app/rds/reservations/page.tsx");
  assert.ok(page.includes('enabled: state.tab === "coverage"'));
  assert.ok(page.includes('enabled: state.tab === "reservations" || state.tab === "expiring"'));
  assert.ok(page.includes('enabled: state.tab === "opportunities"'));
  assert.ok(!page.includes("useTheme("));
  assert.ok(!page.includes("resolvedTheme"));
});

test("Reservations keeps expiration and opportunity semantics backend-owned", async () => {
  const page = await source("../app/rds/reservations/page.tsx");
  const query = await source("../lib/rds-reservations-query.mjs");
  assert.ok(query.includes('state.expirationRange || "LE_30"'));
  assert.ok(query.includes('params.set("sort", "expiration")'));
  assert.ok(page.includes('item.expiration_band === "EXPIRED"'));
  assert.ok(page.includes("item.days_remaining < 0"));
  assert.ok(!page.includes("new Date(item.expiration_at)"));
  assert.ok(page.includes("does not calculate acquisition savings"));
  assert.ok(page.includes("recalculate reservation matching"));
});

test("Reservations uses PercentageDisplay without page-local utilization thresholds", async () => {
  const page = await source("../app/rds/reservations/page.tsx");
  assert.ok(page.includes("<PercentageDisplay value={item.utilization_percentage}"));
  assert.ok(!page.includes("utilization_percentage < 60"));
  assert.ok(!page.includes("Math.min(100"));
});

test("Reservations page does not take scroll ownership from Application Shell", async () => {
  const css = await source("../app/rds/reservations/rds-reservations.module.css");
  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.ok(!css.includes("overflow-x: auto"));
});

test("Reservations files pass the Aven hardcode gate independently", async () => {
  const entries = [
    ["app/rds/reservations/page.tsx", await source("../app/rds/reservations/page.tsx")],
    ["app/rds/reservations/rds-reservations.module.css", await source("../app/rds/reservations/rds-reservations.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});

test("Reservations documentation records the functional regression contracts", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_RESERVATIONS.md", import.meta.url), "utf8");
  for (const phrase of [
    "30-Day Expiration Rule", "Expired Reservation", "Opportunity Matching",
    "does not fabricate", "Theme changes do not participate in query keys",
  ]) assert.ok(docs.includes(phrase), `missing documentation contract: ${phrase}`);
});
