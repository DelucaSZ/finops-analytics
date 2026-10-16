import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  areAllBillingAccountsSelected,
  billingAccountIdsForSelectAll,
  hasBillingAccountSelection,
  parseBillingAccountIds,
} from "../lib/billing-dashboard.mjs";

test("Billing starts without account selection when the URL has no explicit accounts", () => {
  assert.deepEqual(parseBillingAccountIds(null, [1, 2, 3]), []);
  assert.deepEqual(parseBillingAccountIds("", [1, 2, 3]), []);
  assert.equal(hasBillingAccountSelection([]), false);
});

test("Billing restores only explicitly selected and available accounts", () => {
  assert.deepEqual(parseBillingAccountIds("2", [1, 2, 3]), [2]);
  assert.deepEqual(parseBillingAccountIds("3,1,3,999,invalid", [1, 2, 3]), [1, 3]);
  assert.equal(hasBillingAccountSelection([2]), true);
  assert.equal(hasBillingAccountSelection([1, 3]), true);
});

test("select all is explicit and deselecting all returns to an empty selection", () => {
  assert.equal(areAllBillingAccountsSelected([1, 2, 3], []), false);
  assert.equal(areAllBillingAccountsSelected([1, 2, 3], [1, 2]), false);
  assert.equal(areAllBillingAccountsSelected([1, 2, 3], [3, 2, 1]), true);
  assert.deepEqual(billingAccountIdsForSelectAll(true, [3, 1, 2]), [1, 2, 3]);
  assert.deepEqual(billingAccountIdsForSelectAll(false, [1, 2, 3]), []);
});

test("Billing page guards cost requests and persists explicit account IDs", async () => {
  const page = await readFile(new URL("../app/billing/page.tsx", import.meta.url), "utf8").catch(() => "");
  if (!page) return;

  assert.ok(page.includes("const initialAccounts = parseBillingAccountIds("));
  assert.ok(page.includes("params.get(\"accounts\")"));
  assert.ok(page.includes("if (hasAccountSelection) params.set(\"accounts\", selectedAccountIds.join(\",\"));"));
  assert.ok(page.includes("!hasBillingAccountSelection(selectedAccountIds)"));
  assert.ok(page.includes("Selecione ao menos uma conta para consultar os custos."));
  assert.ok(!page.includes(": awsAccounts.map((account) => account.id)"));
});
