import assert from "node:assert/strict";
import test from "node:test";
import {
  buildHistorySnapshotQuery,
  chooseHistoryCycle,
  cycleStateLabel,
  historyMoneyRows,
} from "../lib/opportunity-history.mjs";

test("history snapshots require an explicit cycle and preserve pagination/sort filters", () => {
  assert.equal(buildHistorySnapshotQuery({}), "");
  const query = new URLSearchParams(buildHistorySnapshotQuery({
    cycleId: "cycle-oct",
    page: 2,
    pageSize: 25,
    provider: "aws",
    status: "treated",
    severity: "high",
    search: "i-123",
  }));
  assert.equal(query.get("cycle_id"), "cycle-oct");
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("page_size"), "25");
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("status"), "treated");
  assert.equal(query.get("severity"), "high");
  assert.equal(query.get("search"), "i-123");
  assert.equal(query.get("sort"), "estimated_savings");
  assert.equal(query.get("order"), "desc");
});

test("cycle selector prefers requested cycle then latest closed cycle", () => {
  const cycles = [
    { id: "nov", status: "OPEN" },
    { id: "oct", status: "CLOSED" },
    { id: "sep", status: "CLOSED" },
  ];
  assert.equal(chooseHistoryCycle(cycles, "sep").id, "sep");
  assert.equal(chooseHistoryCycle(cycles).id, "oct");
  assert.equal(chooseHistoryCycle([], "sep"), null);
});

test("open and closed cycles have explicit UX labels", () => {
  assert.equal(cycleStateLabel("OPEN"), "Em andamento");
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
