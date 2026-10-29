import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

function block(source, start, end) {
  const from = source.indexOf(start);
  const to = source.indexOf(end, from + start.length);
  assert.ok(from >= 0, `missing block start: ${start}`);
  assert.ok(to > from, `missing block end: ${end}`);
  return source.slice(from, to);
}

test("single selectors keep empty-state copy inside the select and do not render loose clear actions", () => {
  const source = read("components", "aven", "selectors.tsx");

  assert.match(source, /clearable \? \[\{ value: "", label: placeholder \}\] : \[\]/);
  assert.match(source, /placeholder=\{!clearable && hasOptions \? placeholder : undefined\}/);
  assert.doesNotMatch(source, /styles\.selectorActions/);
  assert.match(source, /selection\.onChange\(\[\]\)/);
  assert.match(source, /\{clearLabel\}/);
});

test("AccountSelector search is opt-in for single selection and remains available for multi-select", () => {
  const source = read("components", "aven", "selectors.tsx");
  assert.match(source, /searchable=\{props\.searchable \?\? Boolean\(props\.multiple\)\}/);
});

test("FilterBar exposes primary, secondary and action regions in logical tab order", () => {
  const source = read("components", "aven", "layout.tsx");
  const primary = source.indexOf('data-aven-filter-group="primary"');
  const secondary = source.indexOf('data-aven-filter-group="secondary"');
  const actions = source.indexOf('data-aven-filter-actions=""');

  assert.ok(primary >= 0);
  assert.ok(secondary > primary);
  assert.ok(actions > secondary);
  assert.match(source, /data-aven-filter-bar/);
  assert.match(source, /data-aven-filter-item/);
  assert.match(source, /FilterItemSize = "compact" \| "default" \| "wide" \| "fluid"/);
});

test("shared FilterBar keeps token-based field widths and predictable wrapping", () => {
  const styles = read("components", "aven", "product-components.module.css");

  assert.match(styles, /\.filterPrimary,[\s\S]*flex-wrap:\s*wrap/);
  assert.match(styles, /--filter-field-default-inline-size/);
  assert.match(styles, /--filter-field-min-inline-size/);
  assert.match(styles, /filterItem\[data-size="compact"\]/);
  assert.match(styles, /filterItem\[data-size="wide"\]/);
  assert.match(styles, /filterItem\[data-size="fluid"\]/);
  assert.match(styles, /@media \(max-width: 48rem\)[\s\S]*flex-basis:\s*100%/);
  assert.doesNotMatch(styles, /\.filterBar\s*\{[^}]*position:\s*absolute/s);
});

test("Inventory has one contextual Search and one instance of each primary shared filter", () => {
  const page = read("app", "inventory", "page.tsx");
  const filters = block(page, "function InventoryFilters", "function InventoryContent");

  assert.equal((filters.match(/<Input\b/g) ?? []).length, 1);
  assert.equal((filters.match(/<ProviderSelector\b/g) ?? []).length, 1);
  assert.equal((filters.match(/<AccountSelector\b/g) ?? []).length, 1);
  for (const label of ["Search", "Provider", "Account", "Region", "Resource type", "Service", "Lifecycle", "Presence"]) {
    assert.equal((filters.match(new RegExp(`label=\\"${label}\\"`, "g")) ?? []).length, 1, `${label} should appear once`);
  }
  assert.match(filters, /clearAction=\{<Button[^>]*>Clear filters<\/Button>\}/);
  assert.doesNotMatch(filters, /<AccountSelector[\s\S]*?searchable=\{true\}/);
});

test("target analytical pages consume the shared filter architecture", () => {
  const opportunities = read("app", "opportunities", "page.tsx");
  const billing = read("app", "billing", "page.tsx");
  const reservations = read("app", "rds", "reservations", "page.tsx");

  for (const source of [opportunities, billing, reservations]) assert.match(source, /<FilterBar/);
  assert.match(opportunities, /<ProviderSelector/);
  assert.match(opportunities, /<AccountSelector/);
  assert.match(opportunities, /isHistory/);
  assert.match(billing, /<AccountSelector/);
  assert.match(billing, /multiple/);
  assert.match(billing, /<DateRangePicker/);
  assert.match(reservations, /<AccountSelector/);
});

test("Aven shared filter changes introduce no forbidden visual hardcodes", () => {
  const entries = [
    ["components/aven/layout.tsx", read("components", "aven", "layout.tsx")],
    ["components/aven/selectors.tsx", read("components", "aven", "selectors.tsx")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});
