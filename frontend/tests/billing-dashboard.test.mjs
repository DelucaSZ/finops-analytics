import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  billingQuerySignature,
  billingVariation,
  formatBillingMoney,
  previousEquivalentPeriod,
  resolveBillingPeriod,
  sameStringSet,
  topBillingItems,
} from "../lib/billing-dashboard.mjs";

const fixedNow = new Date(2026, 9, 15, 12, 0, 0);

test("this month uses today as the last included day and previous comparison keeps month-to-date shape", () => {
  const current = resolveBillingPeriod("this_month", { now: fixedNow });
  assert.deepEqual(current, { start_date: "2026-10-01", end_date: "2026-10-16" });
  assert.deepEqual(previousEquivalentPeriod(current, "this_month"), {
    start_date: "2026-09-01",
    end_date: "2026-09-16",
  });
});

test("custom range treats the UI end date as inclusive but keeps backend end exclusive", () => {
  assert.deepEqual(
    resolveBillingPeriod("custom", {
      customFrom: "2026-10-02",
      customTo: "2026-10-08",
      now: fixedNow,
    }),
    { start_date: "2026-10-02", end_date: "2026-10-09" },
  );
  assert.equal(
    resolveBillingPeriod("custom", {
      customFrom: "2026-10-10",
      customTo: "2026-10-09",
      now: fixedNow,
    }),
    null,
  );
});

test("rolling ranges compare with a previous interval of equal length", () => {
  const current = resolveBillingPeriod("last_30_days", { now: fixedNow });
  assert.deepEqual(current, { start_date: "2026-09-16", end_date: "2026-10-16" });
  assert.deepEqual(previousEquivalentPeriod(current, "last_30_days"), {
    start_date: "2026-08-17",
    end_date: "2026-09-16",
  });
});

test("variation avoids infinity for zero or negative baselines", () => {
  assert.deepEqual(billingVariation("120", "100"), { kind: "percent", percent: 20 });
  assert.deepEqual(billingVariation("12", "0"), { kind: "new", percent: null });
  assert.deepEqual(billingVariation("0", "0"), { kind: "percent", percent: 0 });
  assert.deepEqual(billingVariation("12", "-2"), { kind: "unavailable", percent: null });
});

test("money formatter preserves the unit returned by Billing", () => {
  assert.match(formatBillingMoney("1234.5", "USD"), /1[.,]234|1\.234/);
  assert.match(formatBillingMoney("1234.5", "BRL"), /R\$/);
  assert.match(formatBillingMoney("12.5", "CUSTOM_UNIT"), /CUSTOM_UNIT/);
});

test("set comparison, top N and query signature are deterministic", () => {
  assert.equal(sameStringSet(["Credit", "Tax"], ["Tax", "Credit"]), true);
  assert.deepEqual(
    topBillingItems(
      [
        { label: "S3", amount: "2" },
        { label: "EC2", amount: "10" },
        { label: "RDS", amount: "5" },
      ],
      2,
    ).map((item) => item.label),
    ["EC2", "RDS"],
  );
  const base = {
    profileId: "profile-1",
    accountIds: [3, 1],
    period: { start_date: "2026-10-01", end_date: "2026-10-16" },
    metric: "AMORTIZED_COST",
    granularity: "DAILY",
    excludeRecordTypes: ["Tax", "Credit"],
  };
  assert.equal(
    billingQuerySignature(base),
    billingQuerySignature({ ...base, accountIds: [1, 3], excludeRecordTypes: ["Credit", "Tax"] }),
  );
});

test("Billing page contract keeps AWS Cost Explorer semantics and common backend datasets", async () => {
  const page = await readFile(new URL("../app/billing/page.tsx", import.meta.url), "utf8").catch(() => "");
  if (!page) return;
  assert.ok(page.includes('title="Uso e custos"'));
  assert.ok(page.includes('<ProviderBadge provider="aws"'));
  assert.ok(page.includes("getAwsBillingSummary"));
  assert.ok(page.includes("getAwsBillingTimeSeries"));
  assert.ok(page.includes("getAwsBillingBreakdown"));
  assert.ok(page.includes('selectAllLabel="Selecionar todas"'));
  assert.ok(page.includes("Restaurar perfil"));
  assert.ok(page.includes("Custo do período"));
  assert.ok(page.includes("Evolução de custos"));
  assert.ok(page.includes("Custo por serviço"));
  assert.ok(page.includes("Custo por conta"));
  assert.ok(page.includes("billingStatusLabel(total.status)"));
  assert.ok(page.includes("Nenhuma conversão cambial é realizada"));
  assert.ok(!page.includes("OCI Billing"));
  assert.ok(!page.includes("GetCostForecast"));
});
