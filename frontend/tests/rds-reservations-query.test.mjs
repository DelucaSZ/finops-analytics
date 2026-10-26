import test from "node:test";
import assert from "node:assert/strict";
import {
  buildRdsDashboardQuery,
  clampPercentage,
  coverageDisplayModel,
  coverageStatusLabel,
  crossAccountLabel,
  parseRdsReservationSearchParams,
  patchRdsReservationUrl,
  reservationUtilizationDisplay,
} from "../lib/rds-reservations-query.mjs";

test("parses and restores RDS reservation dashboard filters", () => {
  const state = parseRdsReservationSearchParams("tab=reservations&account=123&region=sa-east-1&engine=postgres&instance_class=db.r7g.xlarge&expiration=LE_30&page=3&page_size=100");
  assert.equal(state.tab, "reservations");
  assert.equal(state.account, "123");
  assert.equal(state.region, "sa-east-1");
  assert.equal(state.instanceClass, "db.r7g.xlarge");
  assert.equal(state.expirationRange, "LE_30");
  assert.equal(state.page, 3);
  assert.equal(state.pageSize, 100);
});

test("coverage query sends filters and pagination to backend", () => {
  const state = parseRdsReservationSearchParams("coverage=partial&region=us-east-1&page=2");
  const query = new URLSearchParams(buildRdsDashboardQuery(state, "coverage"));
  assert.equal(query.get("coverage_status"), "PARTIAL");
  assert.equal(query.get("region"), "us-east-1");
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("page_size"), "50");
  assert.equal(query.get("sort"), "account");
});

test("expiring query defaults to backend <=30 day filter", () => {
  const state = parseRdsReservationSearchParams("tab=expiring");
  const query = new URLSearchParams(buildRdsDashboardQuery(state, "expiring"));
  assert.equal(query.get("expiration_range"), "LE_30");
  assert.equal(query.get("sort"), "expiration");
  assert.equal(query.get("order"), "asc");
});

test("URL patch resets to concise shareable params", () => {
  const state = parseRdsReservationSearchParams("");
  const url = patchRdsReservationUrl(state, { tab: "coverage", coverageStatus: "UNCOVERED", page: 1 });
  assert.equal(url, "?coverage=uncovered");
});

test("coverage labels preserve UNKNOWN as neutral instead of uncovered", () => {
  assert.equal(coverageStatusLabel("FULL"), "Full");
  assert.equal(coverageStatusLabel("PARTIAL"), "Partial");
  assert.equal(coverageStatusLabel("UNCOVERED"), "Uncovered");
  assert.equal(coverageStatusLabel("UNKNOWN"), "Unable to determine");
});

test("coverage percentage helper clamps invalid backend values", () => {
  assert.equal(clampPercentage(100), 100);
  assert.equal(clampPercentage(50), 50);
  assert.equal(clampPercentage(-1), 0);
  assert.equal(clampPercentage(110), 100);
});

test("full coverage payload renders 100% and 8 / 8 NU", () => {
  const model = coverageDisplayModel({ required_units: 8, covered_units: 8, coverage_percentage: 100, coverage_status: "FULL" });
  assert.equal(model.label, "Full");
  assert.equal(model.percentage, 100);
  assert.equal(model.capacity, "8 NU / 8 NU");
});

test("partial coverage payload keeps the explicit gap", () => {
  const model = coverageDisplayModel({ required_units: 16, covered_units: 8, coverage_percentage: 50, coverage_status: "PARTIAL" });
  assert.equal(model.label, "Partial");
  assert.equal(model.percentage, 50);
  assert.equal(model.capacity, "8 NU / 16 NU");
  assert.equal(model.uncovered, "8 NU");
  assert.equal(model.tone, "warning");
});

test("uncovered payload stays uncovered and does not infer savings", () => {
  const model = coverageDisplayModel({ required_units: 8, covered_units: 0, coverage_percentage: 0, coverage_status: "UNCOVERED" });
  assert.equal(model.label, "Uncovered");
  assert.equal(model.percentage, 0);
  assert.equal(model.capacity, "0 NU / 8 NU");
});

test("unknown payload remains neutral", () => {
  const model = coverageDisplayModel({ required_units: 0, covered_units: 0, coverage_percentage: 0, coverage_status: "UNKNOWN" });
  assert.equal(model.label, "Unable to determine");
  assert.equal(model.tone, "neutral");
});

test("unused capacity payload renders backend utilization without recalculation rules", () => {
  const model = reservationUtilizationDisplay({ total_capacity: 16, allocated_capacity: 8, unused_capacity: 8, utilization_percentage: 50 });
  assert.equal(model.percentage, 50);
  assert.equal(model.capacity, "8 NU / 16 NU");
  assert.equal(model.unused, "8 NU");
});

test("cross-account potential is never presented as verified", () => {
  assert.equal(crossAccountLabel("CROSS_ACCOUNT_VERIFIED"), "Cross-account · Verified");
  assert.equal(crossAccountLabel("CROSS_ACCOUNT_POTENTIAL"), "Potential");
});
