import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  aggregateBillingStatuses,
  billingStatusLabel,
  mapBillingTimeSeriesToChartData,
} from "../lib/billing-dashboard.mjs";


test("billing status labels keep actual estimated partial and forecast distinct", () => {
  assert.equal(billingStatusLabel("ACTUAL"), "Realizado");
  assert.equal(billingStatusLabel("ESTIMATED"), "Estimado");
  assert.equal(billingStatusLabel("PARTIALLY_ESTIMATED"), "Parcialmente estimado");
  assert.equal(billingStatusLabel("FORECAST"), "Forecast");
  assert.equal(billingStatusLabel("INCLUDES_FORECAST"), "Inclui forecast");
});


test("status aggregation does not turn one provisional bucket into a fully estimated period", () => {
  assert.equal(
    aggregateBillingStatuses(["ACTUAL", "ACTUAL", "ESTIMATED"]),
    "PARTIALLY_ESTIMATED",
  );
  assert.equal(aggregateBillingStatuses(["ACTUAL", "ACTUAL"]), "ACTUAL");
});


test("chart mapper preserves each daily bucket status", () => {
  const [dataset] = mapBillingTimeSeriesToChartData([
    {
      start_date: "2026-10-21",
      end_date: "2026-10-22",
      amount: "10",
      currency: "USD",
      status: "ACTUAL",
      estimated: false,
      groups: [],
    },
    {
      start_date: "2026-10-22",
      end_date: "2026-10-23",
      amount: "12",
      currency: "USD",
      status: "ACTUAL",
      estimated: false,
      groups: [],
    },
    {
      start_date: "2026-10-23",
      end_date: "2026-10-24",
      amount: "8",
      currency: "USD",
      status: "ESTIMATED",
      estimated: true,
      groups: [],
    },
  ], "NONE");

  assert.deepEqual(dataset.periods.map((period) => period.status), [
    "ACTUAL",
    "ACTUAL",
    "ESTIMATED",
  ]);
  assert.equal(dataset.status, "PARTIALLY_ESTIMATED");
  assert.equal(dataset.periods[0].estimated, false);
  assert.equal(dataset.periods[2].estimated, true);
});


test("forecast remains explicit and is not exposed through the legacy estimated flag", () => {
  const [dataset] = mapBillingTimeSeriesToChartData([
    {
      start_date: "2026-10-24",
      end_date: "2026-10-25",
      amount: "9",
      currency: "USD",
      status: "FORECAST",
      estimated: false,
      groups: [],
    },
  ], "NONE");

  assert.equal(dataset.status, "FORECAST");
  assert.equal(dataset.estimated, false);
  assert.equal(dataset.periods[0].status, "FORECAST");
  assert.equal(dataset.periods[0].series[0].status, "FORECAST");
});


test("Billing UI renders canonical status in summary breakdown and daily tooltip", async () => {
  const page = await readFile(new URL("../app/billing/page.tsx", import.meta.url), "utf8");
  const chart = await readFile(new URL("../app/billing/billing-cost-chart.tsx", import.meta.url), "utf8");

  assert.ok(page.includes("billingStatusLabel(item.status)"));
  assert.ok(page.includes("billingStatusLabel(total.status)"));
  assert.ok(chart.includes("billingStatusLabel(hoveredPeriod.status)"));
  assert.ok(chart.includes("fillOpacity={statusOpacity(item.status)}"));
  assert.ok(chart.includes('strokeDasharray={hasForecast ? "4 3" : undefined}'));
});
