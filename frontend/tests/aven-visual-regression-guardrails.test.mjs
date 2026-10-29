import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanAddedLines, scanText } from "../scripts/check-design-system.mjs";
import {
  VISUAL_GUARDRAIL_ALLOWLIST,
  isVisualGuardrailAllowlisted,
} from "../scripts/visual-guardrail-allowlist.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");
const count = (source, value) => source.split(value).length - 1;

function section(source, start, end) {
  const startIndex = source.indexOf(start);
  assert.notEqual(startIndex, -1, `Missing section start: ${start}`);
  const endIndex = source.indexOf(end, startIndex + start.length);
  assert.notEqual(endIndex, -1, `Missing section end: ${end}`);
  return source.slice(startIndex, endIndex);
}

test("controlled visual regressions are rejected across color, spacing, radius and typography", () => {
  const broken = `
    const Broken = () => (
      <div
        className="gap-[21px] w-[237px] rounded-[11px] text-[13px]"
        style={{ color: "#ffffff", lineHeight: "17px" }}
      />
    );
  `;

  const categories = new Set(scanText(broken, "components/example.tsx").map((item) => item.category));
  assert.deepEqual(categories, new Set(["colors", "spacing", "radius", "typography"]));
});

test("new-line visual gate catches additions without charging deleted legacy debt", () => {
  const addedDiff = `diff --git a/frontend/components/example.tsx b/frontend/components/example.tsx
--- a/frontend/components/example.tsx
+++ b/frontend/components/example.tsx
@@ -10,0 +11,1 @@
+const Broken = () => <div className="gap-[21px]" style={{ color: "#fff" }} />;
`;
  const violations = scanAddedLines(addedDiff);

  assert.equal(violations.length, 2);
  assert.deepEqual(new Set(violations.map((item) => item.category)), new Set(["colors", "spacing"]));
  assert.ok(violations.every((item) => item.filename === "components/example.tsx"));
  assert.ok(violations.every((item) => item.line === 11));

  const deletedOnlyDiff = `diff --git a/frontend/components/example.tsx b/frontend/components/example.tsx
--- a/frontend/components/example.tsx
+++ b/frontend/components/example.tsx
@@ -11,1 +10,0 @@
-const Broken = () => <div style={{ color: "#fff" }} />;
`;
  assert.equal(scanAddedLines(deletedOnlyDiff).length, 0);
});

test("visual guardrail allowlist stays exact, small and documented", () => {
  assert.ok(VISUAL_GUARDRAIL_ALLOWLIST.length > 0);
  assert.ok(VISUAL_GUARDRAIL_ALLOWLIST.length <= 5);
  for (const entry of VISUAL_GUARDRAIL_ALLOWLIST) {
    assert.ok(entry.path);
    assert.ok(entry.reason.length >= 20);
    assert.doesNotMatch(entry.path, /[*?]/);
  }
  assert.equal(isVisualGuardrailAllowlisted("frontend/app/globals.css"), true);
  assert.equal(isVisualGuardrailAllowlisted("components/example.tsx"), false);
});

test("AvenLogo keeps surface-aware official assets and mark contract", () => {
  const logo = read("components", "brand", "brand-logo.tsx");
  const brand = read("lib", "brand.ts");

  assert.match(logo, /surface === "dark" \? "onDark" : "onLight"/);
  assert.match(logo, /variant === "mark"\) return brand\.assets\.mark\.gradient/);
  assert.match(logo, /return brand\.assets\.logo\[variant\]\[surfaceKey\]/);
  assert.match(logo, /data-aven-logo=\{resolvedVariant\}/);
  assert.doesNotMatch(logo, /src=\{AVEN_VECTOR_(?:WORDMARK|SYMBOL)_FALLBACK\}/);

  const requiredAssets = [
    "aven-logo-horizontal-on-dark.png",
    "aven-logo-horizontal-on-light.png",
    "aven-logo-vertical-on-dark.png",
    "aven-logo-vertical-on-light.png",
    "aven-mark-gradient.png",
    "favicon.ico",
  ];

  for (const asset of requiredAssets) {
    assert.match(brand, new RegExp(asset.replaceAll(".", "\\.")));
    assert.equal(
      fs.existsSync(path.join(ROOT, "public", "brand", "aven", asset)),
      true,
      `Missing official asset ${asset}`,
    );
  }
});

test("Login branding is delegated to AvenLogo instead of a textual AVEN facsimile", () => {
  const login = read("app", "login", "page.tsx");
  const authLayout = read("components", "auth", "auth-layout.tsx");

  assert.match(login, /<AuthLayout>/);
  assert.match(authLayout, /<AvenLogo[\s\S]*variant="vertical"[\s\S]*surface=\{surface\}/);
  assert.match(authLayout, /<AvenLogo[\s\S]*variant="horizontal"[\s\S]*surface=\{surface\}/);
  assert.doesNotMatch(authLayout, />\s*AVEN\s*</i);
  assert.doesNotMatch(authLayout, /<svg\b/i);
});

test("Sidebar keeps official wordmark plus mark and collapse is a persisted shell state", () => {
  const shell = read("components", "app-shell", "application-shell.tsx");
  const styles = read("components", "app-shell", "app-shell.module.css");

  assert.match(shell, /<BrandLogo variant="wordmark" decorative \/>/);
  assert.match(shell, /<BrandLogo variant="symbol" decorative \/>/);
  assert.match(
    shell,
    /document\.documentElement\.dataset\.sidebar = next \? "collapsed" : "expanded"/,
  );
  assert.match(shell, /SIDEBAR_STORAGE_KEY/);
  assert.match(styles, /data-sidebar="collapsed"/);
});

test("Inventory owns exactly one shared FilterBar composition with the consolidated fields", () => {
  const inventory = read("app", "inventory", "page.tsx");
  const filters = section(inventory, "function InventoryFilters", "function InventoryContent");
  const labels = ["Search", "Provider", "Account", "Region", "Resource type", "Service", "Lifecycle", "Presence"];

  assert.match(inventory, /FilterBar/);
  assert.match(filters, /<FilterBar/);
  assert.equal(count(filters, "<FilterBar"), 1);
  assert.match(filters, /clearAction=\{/);
  assert.equal(count(filters, "Clear filters"), 1);
  assert.doesNotMatch(inventory, /function\s+FilterBar\s*\(/);

  for (const label of labels) {
    assert.equal(count(filters, `label="${label}"`), 1, `${label} must appear exactly once in Inventory filters`);
  }
});

test("shared FilterBar and PageContainer expose stable semantic layout contracts", () => {
  const layout = read("components", "aven", "layout.tsx");

  assert.match(layout, /export type PageWidth = "standard" \| "wide" \| "full"/);
  assert.match(layout, /data-aven-page-container=""/);
  assert.match(layout, /data-aven-filter-bar=""/);
  assert.match(layout, /data-aven-filter-group="primary"/);
  assert.match(layout, /data-aven-filter-group="secondary"/);
  assert.match(layout, /data-aven-filter-actions=""/);
  assert.match(layout, /\{clearAction\}\{actions\}/);
});

test("Opportunities keeps Impact and Confidence in the non-clipping status stack", () => {
  const opportunities = read("app", "opportunities", "page.tsx");
  const styles = read("app", "opportunities", "opportunities.module.css");
  const headerIndex = opportunities.indexOf("Impacto / confiança");
  assert.notEqual(headerIndex, -1);

  const cellIndex = opportunities.indexOf("className={styles.statusStack}", headerIndex);
  assert.notEqual(cellIndex, -1);
  const cell = opportunities.slice(cellIndex, opportunities.indexOf("</TableCell>", cellIndex));

  assert.match(cell, /Impacto:/);
  assert.match(cell, /Confiança:/);
  assert.doesNotMatch(cell, /truncate|overflow-hidden|text-overflow/i);
  assert.match(styles, /\.statusStack\s*\{/);
});

test("Table architecture owns internal overflow and keeps critical cells non-truncating", () => {
  const table = read("components", "ui", "table.tsx");
  const styles = read("components", "ui", "table.module.css");

  for (const kind of ["status", "badge", "currency", "actions"]) {
    assert.match(table, new RegExp(`"${kind}"`));
  }
  assert.match(styles, /\.tableWrapper\s*\{[\s\S]*overflow-x:\s*auto/);
  assert.match(styles, /\.tableCell\s*\{[\s\S]*overflow:\s*visible/);
  assert.match(styles, /data-column-kind="badge"[\s\S]*min-inline-size:/);
  assert.match(styles, /data-column-kind="status"[\s\S]*min-inline-size:/);
  assert.match(styles, /data-column-kind="currency"[\s\S]*white-space:\s*nowrap/);
  assert.match(styles, /data-column-kind="actions"[\s\S]*white-space:\s*nowrap/);
});

test("page and table layout keep shrink-safe contracts that prevent page-level overflow", () => {
  const shell = read("components", "app-shell", "app-shell.module.css");
  const pageLayout = read("app", "layout-system.css");
  const table = read("components", "ui", "table.module.css");

  assert.match(shell, /minmax\(0, 1fr\)/);
  assert.match(shell, /min-inline-size:\s*var\(--space-0\)/);
  assert.match(pageLayout, /container-type:\s*inline-size/);
  assert.match(table, /max-inline-size:\s*100%/);
  assert.match(table, /overflow-x:\s*auto/);
});
