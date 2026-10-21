import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  buildHistorySnapshotQuery,
  chooseHistoryCycle,
  cycleStateLabel,
  historyMoneyRows,
} from "../lib/opportunity-history.mjs";

const pageSource = readFileSync(
  new URL("../app/opportunities/history-cycles/page.tsx", import.meta.url),
  "utf8",
);

test("history snapshots require an explicit cycle", () => {
  assert.equal(buildHistorySnapshotQuery({}), "");
});

test("history snapshot query preserves pagination and sort", () => {
  const query = new URLSearchParams(buildHistorySnapshotQuery({
    cycleId: "cycle-oct",
    page: 2,
    pageSize: 25,
  }));
  assert.equal(query.get("cycle_id"), "cycle-oct");
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("page_size"), "25");
  assert.equal(query.get("sort"), "estimated_savings");
  assert.equal(query.get("order"), "desc");
});

test("history snapshot query preserves provider status severity and search filters", () => {
  const query = new URLSearchParams(buildHistorySnapshotQuery({
    cycleId: "cycle-oct",
    provider: "aws",
    status: "treated",
    severity: "high",
    search: "i-123",
  }));
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("status"), "treated");
  assert.equal(query.get("severity"), "high");
  assert.equal(query.get("search"), "i-123");
});

test("cycle selector respects an explicitly selected cycle", () => {
  const cycles = [
    { id: "nov", status: "OPEN" },
    { id: "oct", status: "CLOSED" },
    { id: "sep", status: "CLOSED" },
  ];
  assert.equal(chooseHistoryCycle(cycles, "sep").id, "sep");
});

test("cycle selector defaults to latest closed cycle", () => {
  const cycles = [
    { id: "nov", status: "OPEN" },
    { id: "oct", status: "CLOSED" },
    { id: "sep", status: "CLOSED" },
  ];
  assert.equal(chooseHistoryCycle(cycles).id, "oct");
});

test("cycle selector handles empty history", () => {
  assert.equal(chooseHistoryCycle([], "sep"), null);
});

test("open cycle has explicit in-progress label", () => {
  assert.equal(cycleStateLabel("OPEN"), "Em andamento");
});

test("closed cycle has explicit closed label", () => {
  assert.equal(cycleStateLabel("CLOSED"), "Ciclo fechado");
});

test("financial totals remain separate rows per currency", () => {
  const rows = historyMoneyRows({
    potential_savings: [
      { currency: "USD", amount: "100.00" },
      { currency: "BRL", amount: "200.00" },
    ],
  }, "potential_savings");
  assert.deepEqual(rows.map((row) => row.currency), ["USD", "BRL"]);
});

test("UI identifies open cycles as preview instead of definitive snapshot", () => {
  assert.match(pageSource, /Prévia — período ainda não fechado/);
  assert.match(pageSource, /Snapshots definitivos são materializados somente no fechamento/);
});

test("UI preserves legacy history access", () => {
  assert.match(pageSource, /\/opportunities\?view=history/);
  assert.match(pageSource, /Arquivadas atualmente \/ Histórico legado/);
});

test("UI exposes historical cycle selector", () => {
  assert.match(pageSource, /Período histórico/);
  assert.match(pageSource, /history-cycle/);
});

test("UI exposes closed snapshot lifecycle and presence", () => {
  assert.match(pageSource, /Status no fechamento/);
  assert.match(pageSource, /Presença no fechamento/);
});

test("UI exposes historical financial values and currency-aware formatter", () => {
  assert.match(pageSource, /Custo no período/);
  assert.match(pageSource, /Economia estimada/);
  assert.match(pageSource, /formatMoney\(selected\.current_monthly_cost, selected\.currency\)/);
});

test("UI exposes first and last observation timestamps and occurrence count", () => {
  assert.match(pageSource, /Primeira observação no ciclo/);
  assert.match(pageSource, /Última observação no ciclo/);
  assert.match(pageSource, /Observações no ciclo/);
});

test("UI exposes collection coverage including failed runs", () => {
  assert.match(pageSource, /Cobertura de coletas/);
  assert.match(pageSource, /cycle\.coverage\.failed/);
  assert.match(pageSource, /cycle\.coverage\.running/);
});

test("UI exposes historical empty state and detail link to current opportunity", () => {
  assert.match(pageSource, /Nenhum snapshot encontrado para este ciclo e filtros/);
  assert.match(pageSource, /Ver oportunidade atual/);
  assert.match(pageSource, /estado atual é independente deste snapshot/);
});
