import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("History uses the shared Aven analytical composition instead of local cards and tables", () => {
  const page = read("app", "opportunities", "history-cycles", "page.tsx");
  const styles = read("app", "opportunities", "history-cycles", "page.module.css");

  assert.match(page, /MetricCard/);
  assert.match(page, /<Section/);
  assert.match(page, /<Table density="compact" aria-label="Snapshots do histórico de oportunidades">/);
  assert.match(page, /<TableHead kind="identifier">/);
  assert.match(page, /<TableState state="empty" colSpan=\{8\}>/);
  assert.match(page, /<ProviderBadge provider=\{item\.provider\} \/>/);
  assert.match(page, /<StatusIndicator/);
  assert.doesNotMatch(page, /<table\b/);
  assert.doesNotMatch(styles, /\.tableCard\b/);
  assert.doesNotMatch(styles, /\.tableScroll\b/);
  assert.doesNotMatch(styles, /\.card\b/);
});

test("Flow composition uses the shared layout grid and keeps charts contained", () => {
  const styles = read("app", "flow", "flow-layout.module.css");

  assert.match(styles, /\.page\s*\{[\s\S]*gap:\s*var\(--layout-page-gap\)/);
  assert.match(styles, /\.metricGroups\s*\{[\s\S]*gap:\s*var\(--layout-section-gap\)/);
  assert.match(styles, /--layout-grid-min-metric-inline-size/);
  assert.match(styles, /\.chart\s*\{[\s\S]*max-inline-size:\s*100%[\s\S]*min-inline-size:\s*100%/);
  assert.match(styles, /\.actionLink\s*\{[\s\S]*border-radius:\s*var\(--radius-control\)/);
  assert.doesNotMatch(styles, /14rem/);
  assert.doesNotMatch(styles, /36rem/);
});

test("Dashboard, Opportunities, Inventory, Billing and Reservations retain shared page composition", () => {
  const dashboard = read("components", "executive-dashboard.tsx");
  const opportunities = read("app", "opportunities", "page.tsx");
  const inventory = read("app", "inventory", "page.tsx");
  const billing = read("app", "billing", "page.tsx");
  const reservations = read("app", "rds", "reservations", "page.tsx");

  for (const source of [dashboard, opportunities, inventory, billing, reservations]) {
    assert.match(source, /<PageHeader/);
    assert.match(source, /<Section/);
  }

  for (const source of [dashboard, opportunities, inventory, billing]) {
    assert.match(source, /<FilterBar/);
  }

  for (const source of [opportunities, inventory, billing, reservations]) {
    assert.match(source, /<Table/);
  }

  assert.match(billing, /<ChartCard/);
  assert.match(dashboard, /<MetricCard/);
  assert.match(reservations, /<StatusIndicator/);
});

test("priority analytical page modules share Aven page and grid rhythm", () => {
  const modules = [
    read("components", "executive-dashboard.module.css"),
    read("app", "opportunities", "opportunities.module.css"),
    read("app", "inventory", "inventory.module.css"),
    read("app", "flow", "flow-layout.module.css"),
    read("app", "billing", "billing.module.css"),
    read("app", "rds", "reservations", "rds-reservations.module.css"),
  ];

  for (const styles of modules) {
    assert.match(styles, /--layout-page-gap|gap:\s*var\(--layout-page-gap\)/);
  }

  const opportunities = modules[1];
  const inventory = modules[2];
  const reservations = modules[5];
  assert.match(opportunities, /\.metricsGrid > \*/);
  assert.match(inventory, /\.metricsGrid > \*/);
  assert.match(reservations, /\.metricsGrid > \*/);
});

test("Settings keeps fluid width, shared form rhythm and theme-safe policy controls", () => {
  const layout = read("app", "settings", "layout.tsx");
  const settingsStyles = read("app", "settings", "settings-page.module.css");
  const policyStyles = read("app", "settings", "policies", "page.module.css");

  assert.match(layout, /<PageContainer width="full" className=\{styles\.page\}>/);
  assert.match(settingsStyles, /gap:\s*var\(--layout-grid-gap\)/);
  assert.match(settingsStyles, /grid-template-columns:\s*var\(--layout-grid-columns-2\)/);
  assert.match(policyStyles, /background:\s*var\(--surface-secondary\)/);
  assert.match(policyStyles, /border:\s*1px solid var\(--border-subtle\)/);
  assert.match(policyStyles, /color:\s*var\(--text-secondary\)/);
  assert.doesNotMatch(policyStyles, /#[0-9a-fA-F]{3,8}\b/);
  assert.doesNotMatch(policyStyles, /rgba?\(/);
});
