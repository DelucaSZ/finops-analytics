import test from "node:test";
import assert from "node:assert/strict";
import {
  buildRdsDashboardQuery,
  coverageDisplayModel,
  reservationUtilizationDisplay,
} from "../lib/rds-reservations-query.mjs";

test("expiring query preserves the 30-day backend contract", () => {
  const query = new URLSearchParams(buildRdsDashboardQuery({ page: 1, pageSize: 50 }, "expiring"));
  assert.equal(query.get("expiration_range"), "LE_30");
  assert.equal(query.get("sort"), "expiration");
  assert.equal(query.get("order"), "asc");
});

test("utilization display preserves backend anomalies and missing values", () => {
  assert.equal(reservationUtilizationDisplay({ utilization_percentage: 125 }).percentage, 125);
  assert.equal(reservationUtilizationDisplay({ utilization_percentage: -4 }).percentage, -4);
  assert.equal(reservationUtilizationDisplay({ utilization_percentage: null }).percentage, null);
});

test("coverage display preserves null instead of presenting it as zero", () => {
  assert.equal(coverageDisplayModel({ coverage_status: "UNKNOWN", coverage_percentage: null }).percentage, null);
  assert.equal(coverageDisplayModel({ coverage_status: "FULL", coverage_percentage: 0 }).percentage, 0);
  assert.equal(coverageDisplayModel({ coverage_status: "PARTIAL", coverage_percentage: 50 }).percentage, 50);
  assert.equal(coverageDisplayModel({ coverage_status: "FULL", coverage_percentage: 100 }).percentage, 100);
});
