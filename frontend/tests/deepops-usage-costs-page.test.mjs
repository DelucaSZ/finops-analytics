import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/settings/usage-costs/page.tsx", import.meta.url);

test("Usage & Costs dashboard consumes telemetry and Cost Engine read models", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('title={t("title")}'));
  assert.ok(page.includes("/usage/cloudwatch/summary"));
  assert.ok(page.includes("/deepops-costs/cloudwatch/${suffix}"));
  assert.ok(page.includes('costQuery("summary")'));
  assert.ok(page.includes('costQuery("timeseries"'));
  assert.ok(page.includes('costQuery("breakdown"'));
  assert.ok(page.includes('group_by: "collection_run"'));
  assert.ok(page.includes('friendlyUsageLabel(item.value === SHARED_ANALYZER ? null : item.value, "analyzer", locale)'));
});

test("dashboard keeps Billing, FX and frontend pricing calculations out of scope", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('description={t("description")}'));
  assert.ok(page.includes('t("noFX")'));
  assert.ok(page.includes("free_tier_applied"));
  assert.ok(page.includes("pricing_verified_at"));
  assert.ok(page.includes("is_complete"));
  assert.ok(page.includes("unpriced_usage"));
  assert.ok(!page.includes("/billing/aws/"));
  assert.ok(!page.includes("usage_quantity * unit_price"));
  assert.ok(!page.includes("usage_quantity * Number"));
});

test("dashboard exposes independent loading/error semantics and stale request protection", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("costLoading"));
  assert.ok(page.includes("usageLoading"));
  assert.ok(page.includes("runsLoading"));
  assert.ok(page.includes('t("telemetryError")'));
  assert.ok(page.includes('t("costError")'));
  assert.ok(page.includes("AbortController"));
  assert.ok(page.includes("sequence.current"));
});

// Locale-specific presentation must preserve serialized query identifiers.
test("Usage & Costs copy follows locale without changing filter keys", async () => {
 const pt = JSON.parse(await readFile(new URL("../i18n/messages/pt-BR.json", import.meta.url), "utf8"));
 const en = JSON.parse(await readFile(new URL("../i18n/messages/en-US.json", import.meta.url), "utf8"));
 assert.deepEqual(Object.keys(pt.settings.usageCosts).sort(), Object.keys(en.settings.usageCosts).sort());
 assert.equal(pt.settings.usageCosts.title, "Uso e custos");
 assert.equal(en.settings.usageCosts.title, "Usage & costs");
 const page = await readFile(pageUrl, "utf8");
 for (const key of ["cloud_account_id", "group_by", "collection_run", "date_from", "date_to"]) assert.ok(page.includes(key));
 assert.ok(page.includes('friendlyUsageLabel(item.value === SHARED_ANALYZER ? null : item.value, "analyzer", locale)'));
});
