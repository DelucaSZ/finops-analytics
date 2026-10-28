import test from "node:test";
import assert from "node:assert/strict";
import {
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  resolveOpportunityTemporalWindow,
} from "../lib/opportunity-query.mjs";

test("last 24h is a real moving window and list/stats use the same bounds", () => {
  const anchor = new Date("2026-10-21T15:00:00.000Z");
  const state = parseOpportunitySearchParams("identified_preset=last_24h");
  const window = resolveOpportunityTemporalWindow(state, anchor);
  assert.equal(window.field, "first_seen");
  assert.equal(window.from, "2026-10-20T15:00:00.000Z");
  assert.equal(window.to, "2026-10-21T15:00:00.000Z");

  const list = new URLSearchParams(buildOpportunityApiQuery(state, { now: anchor }));
  const stats = new URLSearchParams(buildOpportunityStatsQuery(state, { now: anchor }));
  assert.equal(list.get("first_seen_from"), window.from);
  assert.equal(list.get("first_seen_to"), window.to);
  assert.equal(stats.get("first_seen_from"), window.from);
  assert.equal(stats.get("first_seen_to"), window.to);
});

test("7d and 30d presets preserve first-seen semantics by default", () => {
  const anchor = new Date("2026-10-21T12:00:00.000Z");
  for (const [preset, days] of [["last_7d", 7], ["last_30d", 30]]) {
    const state = parseOpportunitySearchParams(`identified_preset=${preset}`);
    const window = resolveOpportunityTemporalWindow(state, anchor);
    assert.equal(window.field, "first_seen");
    assert.equal(
      new Date(window.to).getTime() - new Date(window.from).getTime(),
      days * 24 * 60 * 60 * 1000,
    );
  }
});

test("custom date period is semi-open and can target last_seen", () => {
  const state = parseOpportunitySearchParams(
    "identified_preset=custom&date_field=last_seen&last_seen_from=2026-10-01&last_seen_to=2026-10-10",
  );
  const window = resolveOpportunityTemporalWindow(state, new Date("2026-10-21T12:00:00.000Z"));
  assert.equal(window.field, "last_seen");
  const from = new Date(window.from);
  const to = new Date(window.to);
  assert.equal(from.getFullYear(), 2026);
  assert.equal(from.getMonth(), 9);
  assert.equal(from.getDate(), 1);
  assert.equal(to.getFullYear(), 2026);
  assert.equal(to.getMonth(), 9);
  assert.equal(to.getDate(), 11);
});

test("absolute timestamp deep links remain deterministic after parsing", () => {
  const from = "2026-10-21T10:12:30.000Z";
  const to = "2026-10-21T11:12:30.000Z";
  const state = parseOpportunitySearchParams(
    `first_seen_from=${encodeURIComponent(from)}&first_seen_to=${encodeURIComponent(to)}`,
  );
  const window = resolveOpportunityTemporalWindow(state, new Date("2030-01-01T00:00:00.000Z"));
  assert.equal(state.temporalPreset, "custom");
  assert.equal(window.from, from);
  assert.equal(window.to, to);
});

test("collection discovery mode is shareable and sent to list and stats", () => {
  const state = parseOpportunitySearchParams(
    "provider=aws&account_id=123&collection_run_id=run-3&discovery_type=reappeared",
  );
  assert.equal(state.collectionRunId, "run-3");
  assert.equal(state.discoveryType, "reappeared");

  for (const raw of [buildOpportunityApiQuery(state), buildOpportunityStatsQuery(state)]) {
    const query = new URLSearchParams(raw);
    assert.equal(query.get("provider"), "aws");
    assert.equal(query.get("account_id"), "123");
    assert.equal(query.get("collection_run_id"), "run-3");
    assert.equal(query.get("discovery_type"), "reappeared");
  }
});

test("discovery type is not sent without a target collection", () => {
  const state = parseOpportunitySearchParams("discovery_type=new_vs_previous");
  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(state.discoveryType, "new_vs_previous");
  assert.equal(query.has("discovery_type"), false);
});

test("opportunities UI exposes Aven temporal and discovery contracts", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(new URL("../app/opportunities/page.tsx", import.meta.url), "utf8");
  const detail = await readFile(new URL("../components/opportunity-detail.tsx", import.meta.url), "utf8");

  assert.match(page, /Primeira identificação/);
  assert.match(page, /Última detecção/);
  assert.match(page, /Últimas 24h/);
  assert.match(page, /Últimos 7 dias/);
  assert.match(page, /Últimos 30 dias/);

  const discoveryContracts = [
    ["observed", "Observadas nesta coleta"],
    ["first_seen", "Identificadas pela primeira vez nesta coleta"],
    ["new_vs_previous", "Novas em relação à coleta anterior"],
    ["reappeared", "Reapareceram nesta coleta"],
    ["continued", "Continuaram presentes"],
  ];
  for (const [type, label] of discoveryContracts) {
    assert.ok(page.includes(`${type}: "${label}"`), `expected current Aven label for ${type}`);
  }

  assert.match(detail, /Primeira identificação/);
  assert.match(detail, /Última detecção/);
  assert.match(detail, /first_seen_collection_run_id/);
  assert.match(detail, /last_seen_collection_run_id/);
});
