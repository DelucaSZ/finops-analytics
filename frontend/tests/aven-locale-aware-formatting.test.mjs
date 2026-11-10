import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

import {
  formatLocaleNumber, formatLocaleCurrency, formatLocalePercentage,
  formatLocaleDate, formatLocaleDateTime, formatLocaleDuration, formatLocaleRelative,
} from "../i18n/formatters.mjs";
import {formatMoney, formatNumber, formatAccountLabel} from "../lib/cloud.mjs";
import {formatBillingMoney, formatBillingDate, formatBillingRange, billingQuerySignature, resolveBillingPeriod} from "../lib/billing-dashboard.mjs";
import {formatNu, coverageDisplayModel, reservationUtilizationDisplay, buildRdsDashboardQuery, parseRdsReservationSearchParams} from "../lib/rds-reservations-query.mjs";
import {formatBrlDecimal, normalizeDecimalInput} from "../lib/pricing.mjs";
import {formatUsageCostMoney, formatUsageNumber, formatUsagePeriodLabel, buildUsageCostQuery} from "../lib/deepops-usage-costs.mjs";

const spaces = (value) => value.replace(/[\u00a0\u202f]/g, " ");

test("regional number separators and missing values never mutate input", () => {
  const value = 1234567.89;
  assert.equal(formatLocaleNumber(value, "pt-BR"), "1.234.567,89");
  assert.equal(formatLocaleNumber(value, "en-US"), "1,234,567.89");
  assert.equal(formatLocaleNumber(-1234.5, "pt-BR"), "-1.234,5");
  assert.equal(formatLocaleNumber(0, "en-US"), "0");
  assert.equal(formatLocaleNumber(null, "pt-BR"), "—");
  assert.equal(formatLocaleNumber("invalid", "en-US"), "—");
  assert.equal(formatLocaleNumber(Number.POSITIVE_INFINITY, "en-US"), "—");
  assert.equal(value, 1234567.89);
  assert.equal(formatNumber(1234.5, "pt-BR"), "1.234,5");
  assert.equal(formatNumber(1234.5, "en-US"), "1,234.5");
});

test("money keeps ISO currency and exact decimal strings without FX conversion", () => {
  const amount = "1234.56";
  assert.equal(spaces(formatLocaleCurrency(amount, "USD", "pt-BR")), "US$ 1.234,56");
  assert.equal(spaces(formatLocaleCurrency(amount, "USD", "en-US")), "$1,234.56");
  assert.equal(spaces(formatLocaleCurrency(amount, "BRL", "pt-BR")), "R$ 1.234,56");
  assert.equal(spaces(formatLocaleCurrency(amount, "BRL", "en-US")), "R$1,234.56");
  assert.match(formatLocaleCurrency(amount, "EUR", "en-US"), /1,234\.56/);
  assert.equal(formatLocaleCurrency(null, "USD", "en-US"), "—");
  assert.match(formatLocaleCurrency("-3.5", "USD", "en-US"), /-?\$?-?3\.50/);
  assert.match(formatMoney(amount, "USD", "en-US"), /1,234\.56/);
  assert.match(formatBillingMoney(amount, "USD", "en-US"), /1,234\.56/);
  assert.equal(amount, "1234.56");
  const precise = "12345678901234567890.12345678";
  assert.equal(spaces(formatBrlDecimal(precise, "pt-BR")), "R$ 12.345.678.901.234.567.890,12345678");
  assert.equal(spaces(formatBrlDecimal(precise, "en-US")), "R$12,345,678,901,234,567,890.12345678");
  assert.equal(normalizeDecimalInput("0,12345678"), "0.12345678");
});

test("percentages explicitly distinguish points from fractions", () => {
  assert.equal(formatLocalePercentage(12.5, "pt-BR", {maximumFractionDigits:1}), "12,5%");
  assert.equal(formatLocalePercentage(12.5, "en-US", {maximumFractionDigits:1}), "12.5%");
  assert.equal(formatLocalePercentage(0.125, "en-US", {valueMode:"fraction", maximumFractionDigits:1}), "12.5%");
  assert.equal(formatLocalePercentage(0, "pt-BR"), "0%");
  assert.equal(formatLocalePercentage(100, "en-US"), "100%");
  assert.equal(formatLocalePercentage(-5, "en-US"), "-5%");
  assert.equal(formatLocalePercentage(120, "en-US"), "120%");
  assert.equal(formatLocalePercentage(null, "pt-BR"), "—");
});

test("civil dates retain selected day across locales and time zones", () => {
  assert.equal(formatLocaleDate("2026-11-10", "pt-BR"), "10/11/2026");
  assert.equal(formatLocaleDate("2026-11-10", "en-US"), "11/10/2026");
  assert.equal(formatLocaleDate("2024-02-29", "pt-BR"), "29/02/2024");
  assert.equal(formatLocaleDate("2026-02-29", "pt-BR"), "—");
  assert.equal(formatLocaleDate("2026-12-31", "pt-BR"), "31/12/2026");
  assert.equal(formatBillingDate("2026-11-10", "pt-BR"), "10/11/2026");
  assert.equal(formatBillingDate("2026-11-10", "en-US"), "11/10/2026");
  assert.equal(formatLocaleDate(null, "en-US"), "—");
  assert.equal(formatLocaleDateTime("no timestamp", "en-US"), "—");
});

test("instant timezone changes clock only on explicit request, not on locale switch", () => {
  const instant = "2026-11-10T00:30:00Z";
  const brUtc = formatLocaleDateTime(instant, "pt-BR");
  const enUtc = formatLocaleDateTime(instant, "en-US");
  const brLocal = formatLocaleDateTime(instant, "pt-BR", {timeZone: "America/Sao_Paulo"});
  const enLocal = formatLocaleDateTime(instant, "en-US", {timeZone: "America/Sao_Paulo"});
  assert.match(brUtc, /10\/11\/2026/);
  assert.match(enUtc, /11\/10\/26/);
  assert.match(brLocal, /09\/11\/2026/);
  assert.match(enLocal, /11\/9\/26/);
  const summer = "2026-07-01T00:30:00Z";
  assert.match(formatLocaleDateTime(summer, "en-US", {timeZone: "America/New_York"}), /6\/30\/26/);
  assert.equal(instant, "2026-11-10T00:30:00Z");
});

test("duration, relative time and NU respect locale and technical units", () => {
  assert.equal(formatLocaleDuration(1, "minute", "pt-BR"), "1 minuto");
  assert.equal(formatLocaleDuration(5, "minute", "en-US"), "5 minutes");
  assert.equal(formatLocaleRelative(-5, "minute", "en-US"), "5 minutes ago");
  assert.match(formatLocaleRelative(-5, "minute", "pt-BR"), /5 minutos/);
  assert.equal(formatNu(1234.5, "pt-BR"), "1.234,5 NU");
  assert.equal(formatNu(1234.5, "en-US"), "1,234.5 NU");
  assert.equal(formatNu(0, "en-US"), "0 NU");
});

test("RDS capacities and operational queries remain equal across locale presentation", () => {
  const coverage = {required_units:1234.5, covered_units:1200, coverage_status:"PARTIAL", coverage_percentage:97.205};
  const pt = coverageDisplayModel(coverage, "pt-BR");
  const en = coverageDisplayModel(coverage, "en-US");
  assert.equal(pt.status, en.status);
  assert.equal(pt.percentage, en.percentage);
  assert.notEqual(pt.capacity, en.capacity);
  assert.equal(coverage.required_units, 1234.5);
  const utilized = {allocated_capacity:2.5,total_capacity:4,unused_capacity:1.5,utilization_percentage:62.5};
  assert.equal(reservationUtilizationDisplay(utilized, "en-US").percentage, 62.5);
  const state = parseRdsReservationSearchParams("account=123456789012&region=sa-east-1&page=2");
  const query = buildRdsDashboardQuery(state, "coverage");
  assert.equal(new URLSearchParams(query).get("account"), "123456789012");
  assert.equal(formatAccountLabel(null,"123456789012"), "123456789012");
});

test("Billing date range, usage filters, and decimal pricing inputs are operational invariants", () => {
  const range = {start_date:"2026-10-01",end_date:"2026-10-09"};
  const pt = formatBillingRange(range,"pt-BR");
  const en = formatBillingRange(range,"en-US");
  assert.notEqual(pt,en);
  assert.deepEqual(range,{start_date:"2026-10-01",end_date:"2026-10-09"});
  const querySignature = billingQuerySignature({
    profileId:"profile-1",accountIds:[1],period:range,metric:"AMORTIZED_COST",
    granularity:"DAILY",excludeRecordTypes:["Tax"],
  });
  assert.equal(typeof querySignature,"string");
  assert.deepEqual(resolveBillingPeriod("custom", {customFrom:"2026-10-01",customTo:"2026-10-08",now:new Date("2026-10-20T12:00:00Z")}),range);
  const filters = {date_from:"2026-10-01",date_to:"2026-10-09",cloud_account_id:"123456789012"};
  assert.equal(buildUsageCostQuery(filters),buildUsageCostQuery({...filters}));
  assert.equal(normalizeDecimalInput("1234.56"),"1234.56");
  assert.equal(normalizeDecimalInput("12.123456789"),null);
  assert.match(formatUsageCostMoney("0.00000432","USD","pt-BR"),/0,000004/);
  assert.match(formatUsageCostMoney("0.00000432","USD","en-US"),/0\.000004/);
  assert.equal(formatUsageNumber(1234,"pt-BR"),"1.234");
  assert.equal(formatUsageNumber(1234,"en-US"),"1,234");
  const period = {start_key:"2026-10-01",end_key:"2026-10-09"};
  assert.notEqual(formatUsagePeriodLabel(period,"pt-BR"),formatUsagePeriodLabel(period,"en-US"));
  assert.deepEqual(period,{start_key:"2026-10-01",end_key:"2026-10-09"});
});

test("Client pages receive the active locale rather than sharing mutable global presentation state", async () => {
  for (const p of [
    "../app/opportunities/history-cycles/page.tsx",
    "../app/rds/reservations/page.tsx",
    "../app/settings/usage-costs/page.tsx",
    "../app/settings/pricing/oci/page.tsx",
    "../components/collection-workspace.tsx",
  ]) {
    const source = await readFile(new URL(p, import.meta.url),"utf8");
    assert.match(source,/useLocale\(\)/,p);
  }
});
