import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createTranslator } from "next-intl";
import { validateCatalogFiles } from "../scripts/check-i18n.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (name) => readFileSync(path.join(ROOT, name), "utf8");
const catalog = (locale) => JSON.parse(read("i18n/messages/" + locale + ".json"));
const dashboard = read("components/executive-dashboard.tsx");
const insights = read("components/dashboard-operational-insights.tsx");
const billing = read("app/billing/page.tsx");
const billingChart = read("app/billing/billing-cost-chart.tsx");
const flow = read("app/flow/page.tsx");

test("25.5: catalog parity and ICU message validity", () => {
  const validated = validateCatalogFiles();
  assert.ok(validated.keys >= 500);
  for (const locale of ["pt-BR", "en-US"]) {
    const messages = catalog(locale);
    for (const namespace of ["dashboard", "billing", "flow"]) {
      assert.ok(messages[namespace], namespace + " catalog missing for " + locale);
    }
  }
});

test("25.5: bilingual Dashboard and Operational Insights with correct ICU pluralization", () => {
  for (const [locale, overview, failure, failures] of [
    ["pt-BR", "Visão geral", "1 conta apresentou falha na coleta mais recente.", "2 contas apresentaram falha na coleta mais recente."],
    ["en-US", "Overview", "1 account failed in the most recent collection.", "2 accounts failed in the most recent collection."],
  ]) {
    const t = createTranslator({ locale, messages: catalog(locale), namespace: "dashboard" });
    assert.equal(t("title"), overview);
    assert.equal(t("operational.failureCount", { count: 1 }), failure);
    assert.equal(t("operational.failureCount", { count: 2 }), failures);
    assert.ok(t("comparison.comparable", { count: 2 }));
    assert.ok(t("status.updatedUntil", { date: "2026-11-09" }).includes("2026-11-09"));
  }
  assert.match(dashboard, /useTranslations\("dashboard"\)/);
  assert.match(insights, /useTranslations\("dashboard"\)/);
  assert.match(dashboard, /queryKeys\.dashboard\.summary\(state\.provider, state\.accountId\)/);
  assert.match(insights, /queryKeys\.dashboard\.operationalInsights\(state\.provider, state\.accountId\)/);
  assert.match(dashboard, /scopedDashboardHref\("\/opportunities"/);
  assert.match(dashboard, /<CurrencyDisplay/);
  assert.doesNotMatch(dashboard, /locale="pt-BR"/);
});

test("25.5: Billing labels change but Cost Explorer request, grouping and currency are unchanged", () => {
  for (const [locale, title, cost, selected] of [
    ["pt-BR", "Uso e custos", "Custo amortizado", "2 contas selecionadas"],
    ["en-US", "Usage & Costs", "Amortized cost", "2 accounts selected"],
  ]) {
    const t = createTranslator({ locale, messages: catalog(locale), namespace: "billing" });
    assert.equal(t("title"), title);
    assert.equal(t("metrics.amortized"), cost);
    assert.equal(t("filters.selected", { count: 2 }), selected);
    assert.ok(t("filters.query", {
      count: 2, period: "2026-10-01", granularity: "DAILY",
      grouping: "SERVICE", metric: "AMORTIZED_COST", exclusions: "None",
    }));
  }
  assert.match(billing, /useTranslations\("billing"\)/);
  assert.match(billing, /billingQuerySignature\(\{/);
  assert.match(billing, /account_ids: accountIds/);
  assert.match(billing, /start_date: period\.start_date/);
  assert.match(billing, /end_date: period\.end_date/);
  assert.match(billing, /params\.set\("period", periodPreset\)/);
  assert.match(billing, /selectedAccountIds\.length > 1/);
  assert.match(billing, /periodPreset === "custom"/);
  assert.match(billing, /<FilterItem size="fluid">\{periodPicker\}<\/FilterItem>/);
  assert.match(billingChart, /const OTHER_SERIES_KEY = "__billing_other__"/);
  assert.match(billingChart, /seriesColor\(item\.key\)/);
  assert.match(billingChart, /formatBillingAxisDate\(period\.start_date, granularity, locale\)/);
  assert.doesNotMatch(billing + billingChart, /locale="pt-BR"/);
  assert.doesNotMatch(billingChart, /const (?:OTHER_SERIES_KEY|SERIES_COLORS) = t\(/);
});

test("25.5: Flow language affects presentation, never ledger enums or request payloads", () => {
  for (const [locale, title, reversed, entries, adjustment] of [
    ["pt-BR", "Fluxo", "Revertida", "2 movimentações no escopo. Reversões permanecem visíveis.", "Ajuste"],
    ["en-US", "Flow", "Reversed", "2 entries in scope. Reversals remain visible.", "Adjustment"],
  ]) {
    const t = createTranslator({ locale, messages: catalog(locale), namespace: "flow" });
    assert.equal(t("title"), title);
    assert.equal(t("status.reversed"), reversed);
    assert.equal(t("types.adjustment"), adjustment);
    assert.equal(t("sections.entryCount", { count: 2 }), entries);
    assert.ok(t("charts.bucketTitle", { bucket: "2026-10", saving: 40, reallocation: 5, balance: 35 }));
  }
  assert.match(flow, /useTranslations\("flow"\)/);
  assert.match(flow, /entry_type: entryType,/);
  assert.match(flow, /direction,/);
  assert.match(flow, /amount: normalizedAmount,/);
  assert.match(flow, /manual_entry_request_id: requestId\.current/);
  assert.match(flow, /normalizePositiveDecimal\(amount\)/);
  assert.match(flow, /directionForEntryType\(entryType, adjustmentDirection\)/);
  assert.match(flow, /\/finops\/ledger\/manual/);
  assert.match(flow, /\/finops\/ledger\/\$\{reverseTarget\.id\}\/reverse/);
  assert.match(flow, /body: JSON\.stringify\(\{ reason \}\)/);
  assert.match(flow, /entry\.direction === "CREDIT"/);
  assert.doesNotMatch(flow, /locale="pt-BR"/);
});

test("25.5: translation keys are never used for request identity or backend enums", () => {
  assert.doesNotMatch(billing, /params\.set\([^\n]*t\(/);
  assert.doesNotMatch(flow, /entry_type: t\(/);
  assert.doesNotMatch(flow, /direction: t\(/);
  assert.doesNotMatch(flow, /body: JSON\.stringify\(t\(/);
  assert.doesNotMatch(dashboard, /queryKeys\.[^\n]*t\(/);
});
