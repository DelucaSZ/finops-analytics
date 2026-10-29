import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("shared Table exposes semantic density and column contracts", () => {
  const source = read("components", "ui", "table.tsx");

  assert.match(source, /TableDensity = "compact" \| "default" \| "comfortable"/);
  for (const kind of ["selection", "identifier", "text", "provider", "badge", "status", "numeric", "currency", "date", "actions"]) {
    assert.match(source, new RegExp(`"${kind}"`), `${kind} should be a supported semantic column kind`);
  }
  assert.match(source, /data-density=\{density\}/);
  assert.match(source, /data-column-kind=\{kind\}/);
  assert.match(source, /kind === "numeric" \|\| kind === "currency"/);
  assert.match(source, /scope=\{props\.scope \?\? "col"\}/);
});

test("shared Table keeps analytical overflow inside the table container", () => {
  const styles = read("components", "ui", "table.module.css");

  assert.match(styles, /\.tableWrapper\s*\{[\s\S]*overflow-x:\s*auto/);
  assert.match(styles, /\.table\s*\{[\s\S]*min-inline-size:\s*100%/);
  assert.match(styles, /table-layout:\s*auto/);
  assert.doesNotMatch(styles, /table-layout:\s*fixed/);
  assert.doesNotMatch(styles, /\.tableCell\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(styles, /\.tableCell\s*\{[^}]*overflow:\s*visible/s);
});

test("shared Table centralizes bounded critical columns without blanket nowrap", () => {
  const styles = read("components", "ui", "table.module.css");

  for (const kind of ["selection", "identifier", "text", "provider", "badge", "status", "numeric", "currency", "date", "actions"]) {
    assert.match(styles, new RegExp(`data-column-kind="${kind}"`), `${kind} should have a shared table rule`);
  }
  assert.match(styles, /data-column-kind="badge"[\s\S]*min-inline-size:/);
  assert.match(styles, /data-column-kind="status"[\s\S]*min-inline-size:/);
  assert.match(styles, /data-column-kind="actions"[\s\S]*min-inline-size:/);
  assert.match(styles, /data-column-kind="currency"[\s\S]*white-space:\s*nowrap/);
  assert.match(styles, /data-column-kind="date"[\s\S]*white-space:\s*nowrap/);
  assert.doesNotMatch(styles, /\.tableCell\s*\{[^}]*white-space:\s*nowrap/s);
});

test("Opportunities no longer clips Impact and Confidence through fixed table geometry", () => {
  const page = read("app", "opportunities", "page.tsx");
  const styles = read("app", "opportunities", "opportunities.module.css");

  assert.match(page, /<TableHead>Impacto \/ confiança<\/TableHead>/);
  assert.match(page, /label=\{`Impacto: \$\{humanize\(finding\.severity\)\}`\}/);
  assert.match(page, /label=\{`Confiança: \$\{finding\.confidence/);
  assert.doesNotMatch(styles, /table-layout:\s*fixed/);
  assert.doesNotMatch(styles, /nth-child/);
  assert.doesNotMatch(styles, /overflow:\s*hidden/);
  assert.match(styles, /\.statusStack > \*\s*\{[\s\S]*max-inline-size:\s*none/);
  assert.match(styles, /\.rowActions > \*\s*\{[\s\S]*min-inline-size:\s*max-content/);
});

test("analytical pages retain shared tables and critical display primitives", () => {
  const inventory = read("app", "inventory", "page.tsx");
  const billing = read("app", "billing", "page.tsx");
  const reservations = read("app", "rds", "reservations", "page.tsx");

  for (const source of [inventory, billing, reservations]) {
    assert.match(source, /<Table>/);
    assert.match(source, /<TableHeader>/);
    assert.match(source, /<TableBody/);
  }

  assert.match(inventory, /<ResourceIdentifier/);
  assert.match(inventory, /<ProviderBadge/);
  assert.match(inventory, /<StatusIndicator/);
  assert.match(inventory, /formatDateTime\(resource\.last_seen_at\)/);

  assert.match(billing, /<CurrencyDisplay/);
  assert.match(billing, /<PercentageDisplay/);
  assert.match(billing, /<StatusIndicator/);
  assert.match(billing, /<TableCell numeric>/);

  assert.match(reservations, /<ResourceIdentifier/);
  assert.match(reservations, /<PercentageDisplay/);
  assert.match(reservations, /<StatusIndicator/);
  assert.match(reservations, /formatDate\(item\.expiration_at\)/);
});

test("long cloud identifiers keep recoverable full values", () => {
  const source = read("components", "aven", "resource-identifier.tsx");

  assert.match(source, /compactResourceIdentifier/);
  assert.match(source, /<Tooltip content=\{primaryText\}>/);
  assert.match(source, /<Tooltip content=\{technicalId\}>/);
  assert.match(source, /tabIndex=\{primaryIsCompacted \? 0 : undefined\}/);
  assert.match(source, /tabIndex=\{0\}/);
  assert.match(source, /navigator\.clipboard\.writeText/);
});

test("Task 24.35 shared table changes introduce no forbidden visual hardcodes", () => {
  const entries = [
    ["components/ui/table.tsx", read("components", "ui", "table.tsx")],
    ["components/ui/table.module.css", read("components", "ui", "table.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});
