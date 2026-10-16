import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const flowLayoutUrl = new URL("../app/flow/layout.tsx", import.meta.url);
const flowCssUrl = new URL("../app/flow/flow-layout.module.css", import.meta.url);
const flowPageUrl = new URL("../app/flow/page.tsx", import.meta.url);

test("Flow route contains page content and prevents page-level horizontal overflow", async () => {
  const [layout, css] = await Promise.all([
    readFile(flowLayoutUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(layout.includes("styles.scope"));
  assert.ok(css.includes("max-width: 100%"));
  assert.ok(css.includes("min-width: 0"));
  assert.ok(css.includes("overflow-x: clip"));
  assert.ok(css.includes("overscroll-behavior-inline: contain"));
});

test("Flow filters, metrics and toolbars use responsive grid contracts", async () => {
  const css = await readFile(flowCssUrl, "utf8");

  assert.ok(css.includes("repeat(3, minmax(0, 1fr))"));
  assert.ok(css.includes("repeat(4, minmax(0, 1fr))"));
  assert.ok(css.includes("grid-template-columns: minmax(0, 1fr) minmax(360px, 620px)"));
  assert.ok(css.includes("@media (max-width: 900px)"));
  assert.ok(css.includes("@media (max-width: 640px)"));
});

test("Flow chart caps bars and centers a single-point series", async () => {
  const [page, css] = await Promise.all([
    readFile(flowPageUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(page.includes("function FlowChart"));
  assert.ok(page.includes("cumulative_balance"));
  assert.ok(css.includes("svg rect"));
  assert.ok(css.includes("svg g:only-of-type > rect:first-of-type"));
  assert.ok(css.includes("x: 352px"));
  assert.ok(css.includes("width: 24px"));
});

test("Flow movement table keeps long descriptions and account identifiers contained", async () => {
  const [page, css] = await Promise.all([
    readFile(flowPageUrl, "utf8"),
    readFile(flowCssUrl, "utf8"),
  ]);

  assert.ok(page.includes('aria-label="Movimentações do Fluxo FinOps"'));
  assert.ok(page.includes("entry.account_name || entry.account_id"));
  assert.ok(css.includes("table-layout: fixed"));
  assert.ok(css.includes("overflow-wrap: anywhere"));
  assert.ok(css.includes("word-break: normal"));
  assert.ok(css.includes("text-align: right"));

  assert.ok(page.includes('api<SummaryItem[]>(`/finops/flow/summary?${base}`)'));
  assert.ok(page.includes('api<TimeseriesResponse>(`/finops/flow/timeseries?${chart}`)'));
  assert.ok(page.includes('api<Breakdowns>(`/finops/flow/breakdowns?${base}`)'));
  assert.ok(page.includes('api<FlowEntryPage>(`/finops/flow/entries?${tableQuery}`)'));
  assert.ok(page.includes('api<FlowEntry>("/finops/ledger/manual"'));
});
