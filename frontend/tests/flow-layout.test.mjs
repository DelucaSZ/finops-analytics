import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const flowLayoutUrl = new URL("../app/flow/layout.tsx", import.meta.url);
const flowCssUrl = new URL("../app/flow/flow-layout.module.css", import.meta.url);
const flowPageUrl = new URL("../app/flow/page.tsx", import.meta.url);
const tableCssUrl = new URL("../components/ui/feedback.module.css", import.meta.url);

test("Flow route contains page content and preserves Application Shell scroll ownership", async () => {
  const [layout, css] = await Promise.all([
    readFile(flowLayoutUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(layout.includes("styles.scope"));
  assert.ok(css.includes("max-inline-size: 100%"));
  assert.ok(css.includes("min-inline-size: 0"));
  assert.ok(css.includes("overscroll-behavior-inline: contain"));
  assert.ok(css.includes("overflow-x: auto"));
  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
});

test("Flow filters, metrics and supporting regions use Aven responsive composition", async () => {
  const [page, css] = await Promise.all([
    readFile(flowPageUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(page.includes("<FilterBar>"));
  assert.ok(page.includes("<MetricCard"));
  assert.ok(page.includes("<Section"));
  assert.ok(page.includes("<ChartCard"));
  assert.ok(css.includes("repeat(auto-fit, minmax(min(100%, 14rem), 1fr))"));
  assert.ok(css.includes("repeat(2, minmax(0, 1fr))"));
  assert.ok(css.includes("@media (max-width: 900px)"));
  assert.ok(css.includes("@media (max-width: 640px)"));
  assert.ok(css.includes("grid-template-columns: minmax(0, 1fr)"));
});

test("Flow chart protects zero/single-point geometry and uses visualization tokens", async () => {
  const [page, css] = await Promise.all([
    readFile(flowPageUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(page.includes("function FlowChart"));
  assert.ok(page.includes("cumulative_balance"));
  assert.ok(page.includes("Math.max(...values, 1)"));
  assert.ok(page.includes("/ Math.max(points.length, 1)"));
  assert.ok(page.includes("+ step / 2"));
  assert.ok(page.includes("Math.max(step * 0.22, 3)"));
  assert.ok(css.includes("var(--chart-series-1)"));
  assert.ok(css.includes("var(--chart-series-2)"));
  assert.ok(css.includes("var(--chart-series-3)"));
  assert.ok(css.includes("var(--chart-axis)"));
});

test("Flow movement table contains long identifiers locally and keeps numeric alignment in the shared primitive", async () => {
  const [page, css, tableCss] = await Promise.all([
    readFile(flowPageUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
    readFile(tableCssUrl, "utf8"),
  ]);

  assert.ok(page.includes('aria-label="Movimentações do Fluxo FinOps"'));
  assert.ok(page.includes("entry.account_name || entry.account_id"));
  assert.ok(page.includes("<TableCell numeric>"));
  assert.ok(css.includes("overflow-wrap: anywhere"));
  assert.match(tableCss, /\.tableWrapper\s*\{[^}]*overflow:\s*auto;/s);
  assert.match(tableCss, /\.tableCell\[data-numeric="true"\][\s\S]*text-align:\s*end;/);

  assert.ok(page.includes('api<SummaryItem[]>(`/finops/flow/summary?${base}`)'));
  assert.ok(page.includes('api<TimeseriesResponse>(`/finops/flow/timeseries?${chart}`)'));
  assert.ok(page.includes('api<Breakdowns>(`/finops/flow/breakdowns?${base}`)'));
  assert.ok(page.includes('api<FlowEntryPage>(`/finops/flow/entries?${tableQuery}`)'));
  assert.ok(page.includes('api<FlowEntry>("/finops/ledger/manual"'));
});
