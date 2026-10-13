import test from "node:test";
import assert from "node:assert/strict";
import {
  datetimeLocalToIso,
  formatBrlDecimal,
  normalizeDecimalInput,
  pricingLifecycleStatus,
  pricingStatusLabel,
  sourceLabel,
  unitLabel,
} from "../lib/pricing.mjs";

test("pricing decimal input stays string based and accepts up to 8 decimal places", () => {
  assert.equal(normalizeDecimalInput("0,12345678"), "0.12345678");
  assert.equal(normalizeDecimalInput("1234.56"), "1234.56");
  assert.equal(normalizeDecimalInput("0.123456789"), null);
  assert.equal(normalizeDecimalInput("-1"), null);
  assert.equal(normalizeDecimalInput("abc"), null);
});

test("BRL formatting is explicit without changing the persisted decimal contract", () => {
  assert.equal(formatBrlDecimal("1234.56"), "R$ 1.234,56");
  assert.equal(formatBrlDecimal("0.12345600"), "R$ 0,123456");
  assert.equal(formatBrlDecimal("10.00000000"), "R$ 10,00");
});

test("pricing lifecycle status is derived from enabled and effective dates", () => {
  const now = new Date("2026-10-13T12:00:00Z");
  const base = {
    enabled: true,
    effective_from: "2026-10-01T00:00:00Z",
    effective_until: null,
  };
  assert.equal(pricingLifecycleStatus(base, now), "active");
  assert.equal(
    pricingLifecycleStatus({ ...base, effective_from: "2026-11-01T00:00:00Z" }, now),
    "future",
  );
  assert.equal(
    pricingLifecycleStatus({ ...base, effective_until: "2026-10-10T00:00:00Z" }, now),
    "expired",
  );
  assert.equal(pricingLifecycleStatus({ ...base, enabled: false }, now), "inactive");
  assert.equal(pricingStatusLabel("active"), "Ativo");
});

test("pricing labels expose domain values in readable form", () => {
  assert.equal(unitLabel("OCPU_HOUR"), "OCPU / hora");
  assert.equal(unitLabel("GB_RAM_HOUR"), "GB RAM / hora");
  assert.equal(unitLabel("GB_MONTH"), "GB / mês");
  assert.equal(sourceLabel("IMPORTED_OCI_CALCULATOR"), "Calculadora OCI importada");
  assert.equal(sourceLabel("MANUAL"), "Manual");
});

test("datetime local values are converted to an unambiguous API instant", () => {
  const value = datetimeLocalToIso("2026-10-13T12:30");
  assert.ok(value);
  assert.match(value, /^2026-10-13T/);
  assert.equal(datetimeLocalToIso("invalid"), null);
});
