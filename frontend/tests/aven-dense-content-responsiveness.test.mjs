import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("Task 24.40 keeps dense-table overflow local and establishes a readable default floor", () => {
  const styles = read("components", "ui", "table.module.css");

  assert.match(styles, /\.tableWrapper\s*\{[\s\S]*max-inline-size:\s*100%[\s\S]*min-inline-size:\s*0[\s\S]*overflow-x:\s*auto/);
  assert.match(styles, /\.tableHead,\s*\n\.tableCell\s*\{[\s\S]*min-inline-size:\s*var\(--aven-table-column-text-min\)/);
  assert.match(styles, /\.tableHead,\s*\n\.tableCell\s*\{[\s\S]*overflow-wrap:\s*normal[\s\S]*word-break:\s*normal/);
  assert.match(styles, /data-numeric="true"[\s\S]*min-inline-size:\s*var\(--aven-table-column-numeric-min\)[\s\S]*white-space:\s*nowrap/);
  assert.doesNotMatch(styles, /overflow-wrap:\s*anywhere/);
  assert.doesNotMatch(styles, /word-break:\s*break-all/);
});

test("Task 24.40 protects compact, badge, status, money, date and action columns from destructive wrapping", () => {
  const styles = read("components", "ui", "table.module.css");

  for (const kind of ["selection", "provider", "badge", "status", "numeric", "currency", "date", "actions"]) {
    assert.match(
      styles,
      new RegExp(`data-column-kind="${kind}"[\\s\\S]*white-space:\\s*nowrap`),
      `${kind} should preserve readable inline content`,
    );
  }
});

test("Opportunities preserves financial values and status badges while allowing secondary text to wrap normally", () => {
  const styles = read("app", "opportunities", "opportunities.module.css");

  assert.match(styles, /\.moneyWithPeriod\s*\{[\s\S]*white-space:\s*nowrap/);
  assert.match(styles, /\.statusStack > \*\s*\{[\s\S]*flex:\s*none[\s\S]*max-inline-size:\s*none/);
  assert.match(styles, /\.secondary\s*\{[\s\S]*overflow-wrap:\s*break-word[\s\S]*word-break:\s*normal/);
  assert.doesNotMatch(styles, /overflow-wrap:\s*anywhere/);
  assert.doesNotMatch(styles, /nth-child/);
});

test("Inventory metadata no longer creates letter-by-letter wrapping", () => {
  const styles = read("app", "inventory", "inventory.module.css");

  assert.match(styles, /\.secondary\s*\{[\s\S]*min-inline-size:\s*0[\s\S]*overflow-wrap:\s*break-word[\s\S]*word-break:\s*normal/);
  assert.match(styles, /\.statusStack > \*\s*\{[\s\S]*flex:\s*none/);
  assert.doesNotMatch(styles, /overflow-wrap:\s*anywhere/);
});

test("Collections keeps its legacy history table inside a page-local horizontal scroll region", () => {
  const page = read("app", "collections", "page.tsx");
  const styles = read("app", "collections", "collections.module.css");

  assert.match(page, /import styles from "\.\/collections\.module\.css"/);
  assert.match(page, /className=\{styles\.page\}/);
  assert.match(styles, /data-table-wrap[\s\S]*max-inline-size:\s*100%[\s\S]*min-inline-size:\s*0[\s\S]*overflow-x:\s*auto/);
  assert.match(styles, /collection-table\)[\s\S]*min-inline-size:\s*100%[\s\S]*table-layout:\s*auto/);
  assert.match(styles, /collection-status\)[\s\S]*white-space:\s*nowrap/);
});

test("Billing and Reservations inherit the shared dense table contract without business-logic changes", () => {
  const billing = read("app", "billing", "page.tsx");
  const reservations = read("app", "rds", "reservations", "page.tsx");

  assert.match(billing, /<Table>/);
  assert.match(billing, /<TableCell numeric>/);
  assert.match(billing, /<CurrencyDisplay/);
  assert.match(billing, /<StatusIndicator/);

  assert.match(reservations, /<Table>/);
  assert.match(reservations, /<TableCell numeric>/);
  assert.match(reservations, /<ResourceIdentifier/);
  assert.match(reservations, /<StatusIndicator/);
});

test("long cloud identifiers retain a recoverable full value", () => {
  const source = read("components", "aven", "resource-identifier.tsx");

  assert.match(source, /compactResourceIdentifier/);
  assert.match(source, /<Tooltip content=\{primaryText\}>/);
  assert.match(source, /<Tooltip content=\{technicalId\}>/);
  assert.match(source, /navigator\.clipboard\.writeText/);
});

test("Task 24.40 responsive additions introduce no forbidden visual hardcodes", () => {
  const entries = [
    ["components/ui/table.module.css", read("components", "ui", "table.module.css")],
    ["app/collections/collections.module.css", read("app", "collections", "collections.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));

  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});
