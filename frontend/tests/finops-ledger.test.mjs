import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  accountsForProvider,
  defaultCurrencyForProvider,
  directionForEntryType,
  formatLedgerMoney,
  normalizePositiveDecimal,
  sourceLabel,
} from "../lib/finops-ledger.mjs";

const flowUrl = new URL("../app/flow/page.tsx", import.meta.url);
const legacyUrl = new URL("../app/finops/ledger/page.tsx", import.meta.url);
const navigationUrl = new URL("../components/app-shell/navigation.ts", import.meta.url);

test("manual entry semantics keep direction and provider currency defaults explicit", () => {
  assert.equal(directionForEntryType("SAVING"), "CREDIT");
  assert.equal(directionForEntryType("REALLOCATION"), "DEBIT");
  assert.equal(directionForEntryType("ADJUSTMENT", "CREDIT"), "CREDIT");
  assert.equal(directionForEntryType("ADJUSTMENT", "DEBIT"), "DEBIT");
  assert.equal(defaultCurrencyForProvider("AWS", "BRL"), "USD");
  assert.equal(defaultCurrencyForProvider("oci", "USD"), "BRL");
});

test("account selection is filtered by provider without hardcoding account ids", () => {
  const accounts = [
    { id: 1, provider: "aws" },
    { id: 2, provider: "oci" },
    { id: 3, provider: "AWS" },
  ];
  assert.deepEqual(accountsForProvider(accounts, "aws").map((item) => item.id), [1, 3]);
  assert.deepEqual(accountsForProvider(accounts, "OCI").map((item) => item.id), [2]);
});

test("monetary input stays a positive decimal string", () => {
  assert.equal(normalizePositiveDecimal("2500.00"), "2500.00");
  assert.equal(normalizePositiveDecimal("2500,50"), "2500.50");
  assert.equal(normalizePositiveDecimal("0"), null);
  assert.equal(normalizePositiveDecimal("-100"), null);
});

test("money formatting and origin labels distinguish currencies and provenance", () => {
  assert.equal(formatLedgerMoney("2500.00", "BRL"), "R$ 2.500,00");
  assert.equal(formatLedgerMoney("2500.00", "USD"), "US$ 2,500.00");
  assert.equal(sourceLabel("MANUAL"), "Manual");
  assert.equal(sourceLabel("OPPORTUNITY"), "Oportunidade");
  assert.equal(sourceLabel("SYSTEM"), "Sistema");
});

test("Flow page exposes filters, dimensional KPIs, charts and paginated ledger", async () => {
  const source = await readFile(flowUrl, "utf8");
  assert.ok(source.includes('title={t("title")}'));
  assert.ok(source.includes('t("metrics.savings")'));
  assert.ok(source.includes('t("metrics.reallocated")'));
  assert.ok(source.includes('t("metrics.adjustments")'));
  assert.ok(source.includes('t("metrics.runRateBalance")'));
  assert.ok(source.includes('t("metrics.balance")'));
  assert.ok(source.includes('t("filters.allCurrencies")'));
  assert.ok(source.includes('t("filters.financialBasis")'));
  assert.ok(source.includes('"types.monthlyBasis"'));
  assert.ok(source.includes('"types.oneTime"'));
  assert.ok(source.includes('"periods.thisYear"'));
  assert.ok(source.includes("effective_from"));
  assert.ok(source.includes("effective_to"));
  assert.ok(source.includes('t("sections.evolution")'));
  assert.ok(source.includes("cumulative_balance"));
  assert.ok(source.includes('t("sections.byAccount")'));
  assert.ok(source.includes('t("sections.bySource")'));
  assert.ok(source.includes("/finops/flow/summary"));
  assert.ok(source.includes("/finops/flow/timeseries"));
  assert.ok(source.includes("/finops/flow/breakdowns"));
  assert.ok(source.includes("/finops/flow/entries"));
  assert.ok(source.includes("page_size: 50"));
  assert.ok(source.includes('emptyTitle={t("empty.entries")}'));
  assert.ok(source.includes('emptyDescription={t("empty.entriesDescription")}'));
});

test("Flow reuses ledger mutations and exposes provenance, opportunity links and detail", async () => {
  const source = await readFile(flowUrl, "utf8");
  assert.ok(source.includes('t("actions.new")'));
  assert.ok(source.includes("crypto.randomUUID()"));
  assert.ok(source.includes("normalizePositiveDecimal(amount)"));
  assert.ok(source.includes('"/finops/ledger/manual"'));
  assert.ok(source.includes("/reverse`"));
  assert.ok(source.includes('t("forms.reverseReason")'));
  assert.ok(source.includes("entry.is_reversed"));
  assert.ok(source.includes("entry.is_reversal"));
  assert.ok(source.includes("opportunity_id="));
  assert.ok(source.includes('t("actions.viewOpportunity")'));
  assert.ok(source.includes('t("details.treatment")'));
  assert.ok(source.includes('t("headers.createdBy")'));
});

test("main navigation uses product Flow route and legacy ledger route redirects", async () => {
  const navigation = await readFile(navigationUrl, "utf8");
  const legacy = await readFile(legacyUrl, "utf8");
  assert.ok(navigation.includes('href: "/flow"'));
  assert.ok(navigation.includes('labelKey: "flow"'));
  assert.ok(navigation.includes('href: "/opportunities"'));
  assert.ok(navigation.includes('labelKey: "opportunities"'));
  assert.ok(legacy.includes('redirect("/flow")'));
});
