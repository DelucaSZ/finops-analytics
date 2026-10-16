import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  billingQuerySignature,
  formatBillingAxisDate,
  formatBillingAxisMoney,
  mapBillingTimeSeriesToChartData,
} from "../lib/billing-dashboard.mjs";

const groupedPoints = [
  {
    start_date: "2026-10-01",
    end_date: "2026-10-02",
    amount: "15",
    currency: "USD",
    estimated: false,
    groups: [
      { key: "EC2", label: "Amazon EC2", amount: "10", estimated: false },
      { key: "S3", label: "Amazon S3", amount: "5", estimated: false },
    ],
  },
  {
    start_date: "2026-10-02",
    end_date: "2026-10-03",
    amount: "0",
    currency: "USD",
    estimated: false,
    groups: [],
  },
  {
    start_date: "2026-10-03",
    end_date: "2026-10-04",
    amount: "-3",
    currency: "USD",
    estimated: true,
    groups: [
      { key: "Credit", label: "Credit", amount: "-3", estimated: true },
    ],
  },
];

test("chart mapper builds deterministic stacked periods without truncating grouped data", () => {
  const [dataset] = mapBillingTimeSeriesToChartData(groupedPoints, "SERVICE");

  assert.equal(dataset.currency, "USD");
  assert.equal(dataset.total, 12);
  assert.equal(dataset.estimated, true);
  assert.deepEqual(dataset.series.map((item) => item.key), ["EC2", "S3", "Credit"]);
  assert.deepEqual(dataset.periods.map((period) => period.total), [15, 0, -3]);
  assert.deepEqual(dataset.periods[0].series.map((item) => item.amount), [10, 5]);
  assert.deepEqual(dataset.periods[1].series, []);
  assert.equal(dataset.periods[2].series[0].amount, -3);
});

test("chart mapper keeps a single series when no grouping is selected", () => {
  const [dataset] = mapBillingTimeSeriesToChartData(
    groupedPoints.map(({ groups: _groups, ...point }) => point),
    "NONE",
  );

  assert.deepEqual(dataset.series.map((item) => item.key), ["__total__"]);
  assert.deepEqual(dataset.periods.map((period) => period.series[0].amount), [15, 0, -3]);
});

test("axis formatters adapt dates and compact large values without changing tooltip precision helper", () => {
  assert.equal(formatBillingAxisDate("2026-10-15", "DAILY"), "15/10");
  assert.match(formatBillingAxisDate("2026-10-01", "MONTHLY"), /out|10/i);
  assert.match(formatBillingAxisMoney("12500", "USD"), /12|13/);
  assert.match(formatBillingAxisMoney("-2500", "BRL"), /-/);
});

test("grouping participates in the Billing query signature", () => {
  const base = {
    profileId: "profile-1",
    accountIds: [1],
    period: { start_date: "2026-10-01", end_date: "2026-10-04" },
    metric: "AMORTIZED_COST",
    granularity: "DAILY",
    excludeRecordTypes: ["Credit"],
  };

  assert.notEqual(
    billingQuerySignature({ ...base, groupBy: "NONE" }),
    billingQuerySignature({ ...base, groupBy: "SERVICE" }),
  );
});

test("Billing page exposes grouping and keeps the explicit account guard", async () => {
  const page = await readFile(new URL("../app/billing/page.tsx", import.meta.url), "utf8");
  const chart = await readFile(new URL("../app/billing/billing-cost-chart.tsx", import.meta.url), "utf8");

  assert.ok(page.includes("Agrupamento"));
  assert.ok(page.includes("mapBillingTimeSeriesToChartData"));
  assert.ok(page.includes("!hasBillingAccountSelection(selectedAccountIds)"));
  assert.ok(page.includes("Selecione ao menos uma conta para consultar os custos."));
  assert.ok(chart.includes("Total do período"));
  assert.ok(chart.includes("gridLine"));
  assert.ok(chart.includes("chartTooltip"));
});
