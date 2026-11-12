import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { formatLocaleCurrency, formatLocaleDate, formatLocaleNumber, formatLocalePercentage } from "../i18n/formatters.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const page = read("app", "calculator", "page.tsx");
const css = read("app", "calculator", "calculator.module.css");
const pt = JSON.parse(read("i18n", "messages", "pt-BR.json")).calculator;
const en = JSON.parse(read("i18n", "messages", "en-US.json")).calculator;

const leafKeys = (value, prefix = "") => Object.entries(value).flatMap(([key, item]) =>
  item && typeof item === "object" ? leafKeys(item, prefix + key + ".") : [prefix + key]);

test("calculator localization keys and targeted validation errors have exact parity", () => {
  assert.deepEqual(leafKeys(pt).sort(), leafKeys(en).sort());
  for (const key of ["discountRange", "taxRange", "fxPositive", "fxPrecision",
    "positiveNumber", "quantityRange", "durationRange", "iopsRange", "throughputRange",
    "ecpuRange", "ocpuRange", "memoryRange", "volumeCountRange", "invalidDates"]) {
    assert.ok(pt.errors[key] && en.errors[key], key);
    assert.ok(page.includes('t("errors.' + key + '")'), key + " not referenced by UI");
  }
});

test("presentation localizes USD and BRL without changing either currency", () => {
  assert.match(formatLocaleCurrency("1234.56", "USD", "pt-BR"), /US\$\s*1\.234,56/);
  assert.match(formatLocaleCurrency("1234.56", "USD", "en-US"), /\$1,234\.56/);
  assert.match(formatLocaleCurrency("1234.56", "BRL", "pt-BR"), /R\$\s*1\.234,56/);
  assert.match(formatLocaleCurrency("1234.56", "BRL", "en-US"), /R\$1,234\.56/);
  assert.equal(formatLocaleNumber("1234.56789012", "pt-BR", { maximumFractionDigits: 8 }), "1.234,56789012");
  assert.equal(formatLocaleNumber("1234.56789012", "en-US", { maximumFractionDigits: 8 }), "1,234.56789012");
  assert.match(formatLocalePercentage("13", "pt-BR"), /13\s*%/);
  assert.equal(formatLocaleDate("2026-11-12", "pt-BR"), "12/11/2026");
  assert.match(formatLocaleDate("2026-11-12", "en-US"), /11\/12\/2026/);
});

test("calculator displays backend prices without frontend conversion, hidden or fictitious totals", () => {
  assert.match(page, /estimate\.pricing_status === "priced"/);
  assert.match(page, /currency\(estimate\.monthly_final_cost, estimate\.final_currency\)/);
  assert.match(page, /currency\(estimate\.period_known_subtotal, estimate\.pricing_currency\)/);
  assert.match(page, /formatLocalePercentage\(estimate\.discount_percent, locale\)/);
  assert.match(page, /formatLocaleNumber\(estimate\.usd_brl_rate, locale/);
  assert.match(page, /formatLocaleDateTime\(estimate\.pricing_reference_date, locale\)/);
  assert.match(page, /estimate\.missing_pricing_components\.map/);
  assert.doesNotMatch(page, /monthly_final_cost\s*[+*/-]|period_final_cost\s*[+*/-]/);
});

test("decimal inputs remain locale-flexible while field messages are associated with controls", () => {
  assert.match(page, /const decimal = \["capacity", "bootSize", "dbStorage", "amount", "discount", "tax", "fx"\]/);
  assert.match(page, /type=\{decimal \? "text" : "number"\}/);
  assert.match(page, /inputMode=\{decimal \? "decimal" : "numeric"\}/);
  assert.match(page, /error=\{fieldError\(key\)\}/);
  assert.match(page, /noValidate/);
  assert.match(page, /role="status" aria-live="polite" aria-atomic="true"/);
  assert.match(page, /aria-label=\{id\}/);
});

test("responsive component breakdown preserves full identifiers and theme tokens", () => {
  assert.match(page, /title=\{component\.sku\}/);
  assert.match(page, /title=\{id\} aria-label=\{id\}/);
  assert.match(css, /\.missingList \{/);
  assert.match(css, /\.srOnly \{/);
  assert.match(css, /\.definition \{ grid-template-columns: minmax\(0, 1fr\); \}/);
  assert.match(css, /overflow-x: auto/);
  assert.match(css, /@container aven-page/);
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b/i);
});
