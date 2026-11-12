import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(root, ...parts), "utf8");
const page = read("app", "calculator", "page.tsx");
const client = read("lib", "calculator.ts");
const stylesheet = read("app", "calculator", "calculator.module.css");
const navigation = read("components", "app-shell", "navigation.ts");
const pt = JSON.parse(read("i18n", "messages", "pt-BR.json"));
const en = JSON.parse(read("i18n", "messages", "en-US.json"));

test("calculator is an authenticated shell navigation route localized in both catalogs", () => {
  assert.match(navigation, /href: "\/calculator", labelKey: "calculator"/);
  assert.equal(pt.shell.navigation.calculator, "Calculadora");
  assert.equal(en.shell.navigation.calculator, "Calculator");
  assert.match(page, /<PageContainer width="full"/);
  assert.match(page, /<PageHeader title=\{t\("title"\)\}/);
});
test("calculator uses existing authenticated APIs and never implements financial arithmetic", () => {
  for (const endpoint of ["/calculator/estimate", "/calculator/aws/regions", "/calculator/aws/options", "/calculator/oci/options"]) {
    assert.ok(client.includes(endpoint), endpoint);
  }
  assert.match(client, /return api<CalculatorEstimate>/);
  assert.match(client, /method: "POST"/);
  assert.doesNotMatch(page, /fetch\(|XMLHttpRequest|localStorage|sessionStorage/);
  assert.match(page, /monthly_final_cost/);
  assert.match(page, /period_final_cost/);
  assert.match(page, /monthly_known_subtotal/);
  assert.match(page, /period_known_subtotal/);
  assert.match(page, /estimate\.pricing_status === "priced"/);
});
test("AWS metadata is searched with two characters and requests cannot display a stale result", () => {
  assert.match(page, /search\.length < 2/);
  assert.match(page, /fetchAwsRegions/);
  assert.match(page, /fetchAwsOptions/);
  assert.match(page, /ec2Combinations\.some/);
  assert.match(page, /rdsCombinations\.some/);
  assert.match(page, /requestNumber\.current/);
  assert.match(page, /requestRef\.current\?\.abort\(\)/);
  assert.match(page, /controller\.signal\.aborted/);
});
test("OCI uses backend metadata, no AWS adjustments, and incomplete DB prices cannot be final", () => {
  assert.match(page, /fetchOciOptions/);
  assert.match(page, /ociCompute\?\.operating_systems/);
  assert.match(page, /ociCompute\.vpu_tiers/);
  assert.match(page, /dbOption\.shape !== ociDb\?\.new_provisioning_shape/);
  assert.match(page, /if \(provider === "aws"\) \{/);
  assert.match(page, /ociDb\?\.setup_required/);
  assert.match(page, /!estimate\.pricing_components\.length/);
  assert.match(page, /notFinal/);
});
test("periods retain timezone offsets and validation, financial options keep safe defaults", () => {
  for (const mode of ["monthly", "hours", "days", "weeks", "custom"]) assert.ok(page.includes(mode));
  assert.match(page, /start\.toISOString\(\)/);
  assert.match(page, /end\.toISOString\(\)/);
  assert.match(page, /end\.getTime\(\) <= start\.getTime\(\)/);
  assert.match(page, /discount: "0"/);
  assert.match(page, /tax: "13"/);
  assert.match(page, /fx: ""/);
  assert.match(page, /setConvert\(nextProvider === "aws"/);
  assert.match(page, /request\.aws_financial =/);
  assert.match(page, /nonNegativePercent\(form\.discount, 100\)/);
});
test("official selectors, responsive layout and long-SKU protection are used", () => {
  assert.match(page, /<Select /);
  assert.match(page, /<Switch /);
  assert.match(page, /<Input /);
  assert.match(page, /<Alert /);
  assert.match(page, /compactIdentifier\(component\.sku\)/);
  assert.match(stylesheet, /@container aven-page/);
  assert.match(stylesheet, /grid-template-columns: minmax\(0, 1\.5fr\) minmax\(0, 1fr\)/);
  assert.match(stylesheet, /overflow-x: auto/);
  assert.match(stylesheet, /min-inline-size: 0/);
  assert.doesNotMatch(page, /<select(?=\s|>)/);
});
test("all new UI strings have PT-BR / EN-US catalog parity", () => {
  function flattened(value, prefix = "") {
    return Object.entries(value).flatMap(([key, item]) => item && typeof item === "object"
      ? flattened(item, prefix + key + ".") : [prefix + key]);
  }
  assert.deepEqual(flattened(pt.calculator).sort(), flattened(en.calculator).sort());
  const strings = [...page.matchAll(/\bt\("([a-zA-Z][a-zA-Z0-9]*)"/g)].map((match) => match[1]);
  for (const key of strings) assert.ok(key in pt.calculator, "Missing PT-BR key: " + key);
});
