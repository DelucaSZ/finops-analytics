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

const pageUrl = new URL("../app/finops/ledger/page.tsx", import.meta.url);
const shellUrl = new URL("../components/app-shell.tsx", import.meta.url);

test("manual entry semantics keep direction and provider currency defaults explicit", () => {
  assert.equal(directionForEntryType("SAVING"), "CREDIT");
  assert.equal(directionForEntryType("REALLOCATION"), "DEBIT");
  assert.equal(directionForEntryType("ADJUSTMENT", "CREDIT"), "CREDIT");
  assert.equal(directionForEntryType("ADJUSTMENT", "DEBIT"), "DEBIT");
  assert.equal(defaultCurrencyForProvider("AWS", "BRL"), "USD");
  assert.equal(defaultCurrencyForProvider("oci", "USD"), "BRL");
  assert.equal(defaultCurrencyForProvider("azure", "BRL"), "BRL");
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
  assert.equal(normalizePositiveDecimal("0.00000000"), null);
  assert.equal(normalizePositiveDecimal("-100"), null);
  assert.equal(normalizePositiveDecimal("1.123456789"), null);
});

test("money formatting distinguishes BRL and USD", () => {
  assert.equal(formatLedgerMoney("2500.00", "BRL"), "R$ 2.500,00");
  assert.equal(formatLedgerMoney("2500.00", "USD"), "US$ 2,500.00");
  assert.equal(sourceLabel("MANUAL"), "Manual");
  assert.equal(sourceLabel("OPPORTUNITY"), "Oportunidade");
});

test("minimal Fluxo page exposes create, validation, idempotency and reversal workflows", async () => {
  const source = await readFile(pageUrl, "utf8");

  assert.ok(source.includes('title="Movimentações"'));
  assert.ok(source.includes("Nova movimentação"));
  assert.ok(source.includes("Saving"));
  assert.ok(source.includes("Realocação"));
  assert.ok(source.includes("Ajuste"));
  assert.ok(source.includes("Crédito"));
  assert.ok(source.includes("Débito"));
  assert.ok(source.includes("BRL — Real brasileiro"));
  assert.ok(source.includes("USD — Dólar americano"));
  assert.ok(source.includes("Data da movimentação"));
  assert.ok(source.includes("Periodicidade"));
  assert.ok(source.includes("Descrição"));
  assert.ok(source.includes("crypto.randomUUID()"));
  assert.ok(source.includes("normalizePositiveDecimal(amount)"));
  assert.ok(source.includes("effective > localDateInput()"));
  assert.ok(source.includes('method: "POST"'));
  assert.ok(source.includes('"/finops/ledger/manual"'));
  assert.ok(source.includes("/reverse`"));
  assert.ok(source.includes("Motivo da reversão"));
  assert.ok(source.includes("entry.is_reversed"));
  assert.ok(source.includes("entry.reversal_of_id"));
  assert.ok(source.includes("sourceLabel(entry.source)"));
  assert.ok(source.includes("Nenhuma movimentação registrada."));
  assert.ok(source.includes("Carregando movimentações…"));
  assert.ok(source.includes("Não foi possível registrar a movimentação."));
  assert.ok(source.includes("Não foi possível reverter a movimentação."));
  assert.ok(source.includes("disabled={saving"));
});

test("Fluxo navigation is minimal and does not replace the existing shell", async () => {
  const source = await readFile(shellUrl, "utf8");
  assert.ok(source.includes('{ href: "/finops/ledger", label: "Fluxo"'));
  assert.ok(source.includes('{ href: "/opportunities", label: "Oportunidades"'));
  assert.ok(source.includes('{ href: "/collections", label: "Coletas"'));
});
