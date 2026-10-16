import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/settings/usage-costs/page.tsx", import.meta.url);

test("Usage & Costs dashboard consumes telemetry and Cost Engine read models", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('title="Uso e custos"'));
  assert.ok(page.includes("/usage/cloudwatch/summary"));
  assert.ok(page.includes("/deepops-costs/cloudwatch/${suffix}"));
  assert.ok(page.includes('costQuery("summary")'));
  assert.ok(page.includes('costQuery("timeseries"'));
  assert.ok(page.includes('costQuery("breakdown"'));
  assert.ok(page.includes('group_by: "collection_run"'));
  assert.ok(page.includes("Compartilhado / não atribuído"));
});

test("dashboard keeps Billing, FX and frontend pricing calculations out of scope", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("Não representa a fatura AWS"));
  assert.ok(page.includes("Sem conversão cambial"));
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
  assert.ok(page.includes("Erro de telemetria"));
  assert.ok(page.includes("Erro de pricing/custo"));
  assert.ok(page.includes("AbortController"));
  assert.ok(page.includes("sequence.current"));
});
