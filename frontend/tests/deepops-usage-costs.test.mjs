import assert from "node:assert/strict";
import test from "node:test";

import {
  buildUsageCostQuery,
  costItemsByCurrency,
  formatUsageCostMoney,
  friendlyUsageLabel,
  pricingVersionCount,
  resolveUsageCostPeriod,
  summarizeUsage,
  usageCostGranularity,
} from "../lib/deepops-usage-costs.mjs";

test("this-month is the default monthly operating period with exclusive end", () => {
  const period = resolveUsageCostPeriod("this-month", "", "", new Date(2026, 9, 16, 12));
  assert.equal(period.start_key, "2026-10-01");
  assert.equal(period.end_key, "2026-10-31");
  assert.equal(period.days, 31);
  assert.equal(usageCostGranularity(period), "daily");
});

test("long periods switch to monthly cost buckets", () => {
  const period = resolveUsageCostPeriod("last-3-months", "", "", new Date(2026, 9, 16, 12));
  assert.equal(period.start_key, "2026-08-01");
  assert.equal(period.end_key, "2026-10-31");
  assert.equal(usageCostGranularity(period), "monthly");
});

test("custom period rejects inverted ranges", () => {
  assert.equal(resolveUsageCostPeriod("custom", "2026-10-20", "2026-10-10"), null);
});

test("canonical query omits empty filters and preserves period", () => {
  const query = buildUsageCostQuery({
    date_from: "2026-10-01T03:00:00.000Z",
    date_to: "2026-11-01T03:00:00.000Z",
    cloud_account_id: 7,
    region: "",
    operation: "GetMetricStatistics",
  });
  const params = new URLSearchParams(query.slice(1));
  assert.equal(params.get("cloud_account_id"), "7");
  assert.equal(params.get("operation"), "GetMetricStatistics");
  assert.equal(params.has("region"), false);
});

test("technical usage dimensions are summed independently", () => {
  const total = summarizeUsage([
    { group: "a", events: 2, requests: 3, metric_queries: 0, metrics_requested: 2, failed_events: 0 },
    { group: "b", events: 1, requests: 1, metric_queries: 500, metrics_requested: 0, failed_events: 1 },
  ]);
  assert.deepEqual(total, {
    events: 3,
    requests: 4,
    metric_queries: 500,
    metrics_requested: 2,
    failed_events: 1,
  });
});

test("cost rows remain separated by currency", () => {
  const grouped = costItemsByCurrency([
    { group: "a", period: null, currency: "USD", gross_estimated_cost: "0.02", usage_quantity: "2" },
    { group: "b", period: null, currency: "BRL", gross_estimated_cost: "10", usage_quantity: "1" },
    { group: "c", period: null, currency: "USD", gross_estimated_cost: "0.03", usage_quantity: "3" },
  ]);
  assert.deepEqual(grouped.map(([currency]) => currency), ["BRL", "USD"]);
  assert.deepEqual(grouped[1][1].map((item) => item.group), ["c", "a"]);
});

test("small non-zero costs are not formatted as zero", () => {
  const formatted = formatUsageCostMoney("0.00000432", "USD");
  assert.notEqual(formatted, formatUsageCostMoney("0", "USD"));
  assert.match(formatted, /0,000004/);
});

test("shared analyzer and known collectors get friendly labels", () => {
  assert.equal(friendlyUsageLabel("Shared / Unattributed", "analyzer"), "Compartilhado / não atribuído");
  assert.equal(friendlyUsageLabel("rds_nonprod_idle", "collector"), "RDS — ociosidade não produtiva");
});

test("pricing version count uses backend provenance instead of current-price assumptions", () => {
  assert.equal(
    pricingVersionCount([
      {
        group: null,
        period: null,
        currency: "USD",
        gross_estimated_cost: "1",
        usage_quantity: "1000",
        components: [
          { pricing_rule_id: "rule-a", effective_from: "2026-01-01T00:00:00Z" },
          { pricing_rule_id: "rule-b", effective_from: "2026-10-01T00:00:00Z" },
        ],
      },
    ]),
    2,
  );
});
