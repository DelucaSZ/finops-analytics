import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

test("Application Shell keeps expanded, collapsed and compact layouts shrink-safe", () => {
  const styles = read("components", "app-shell", "app-shell.module.css");

  assert.match(styles, /grid-template-columns:\s*var\(--shell-sidebar-inline-size\) minmax\(0, 1fr\)/);
  assert.match(styles, /data-sidebar="collapsed"[\s\S]*grid-template-columns:\s*var\(--shell-sidebar-collapsed-inline-size\) minmax\(0, 1fr\)/);
  assert.match(styles, /\.workspace\s*\{[\s\S]*min-inline-size:\s*var\(--space-0\)/);
  assert.match(styles, /\.mainContent\s*\{[\s\S]*overflow:\s*auto/);
  assert.match(styles, /@media \(max-width: 850px\)[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/);
  assert.match(styles, /@media \(prefers-reduced-motion: reduce\)/);
});

test("page composition responds to available container width instead of exact viewport hacks", () => {
  const layout = read("app", "layout-system.css");

  assert.match(layout, /container-name:\s*aven-page/);
  assert.match(layout, /container-type:\s*inline-size/);
  assert.match(layout, /@container aven-page \(max-width: 62rem\)/);
  assert.match(layout, /@container aven-page \(max-width: 48rem\)/);
  assert.match(layout, /data-aven-filter-actions/);
  assert.match(layout, /data-aven-filter-group/);
  assert.match(layout, /flex-basis:\s*100%/);
  assert.doesNotMatch(layout, /@media\s*\(\s*width\s*:/);
  assert.doesNotMatch(layout, /1366px|1280px|1024px|768px/);
});

test("Inventory metrics degrade predictably with sidebar-aware content width", () => {
  const styles = read("app", "inventory", "inventory.module.css");

  assert.match(styles, /@container aven-page \(max-width: 78rem\)[\s\S]*--layout-grid-columns-3/);
  assert.match(styles, /@container aven-page \(max-width: 62rem\)[\s\S]*--layout-grid-columns-2/);
  assert.match(styles, /@container aven-page \(max-width: 48rem\)[\s\S]*--layout-grid-columns-1/);
  assert.doesNotMatch(styles, /@media\s*\(\s*width\s*:/);
});

test("tables own horizontal overflow and badges wrap instead of clipping", () => {
  const table = read("components", "ui", "table.module.css");
  const badge = read("components", "ui", "badge.tsx");
  const layout = read("app", "layout-system.css");

  assert.match(table, /\.tableWrapper\s*\{[\s\S]*max-inline-size:\s*100%[\s\S]*overflow-x:\s*auto/);
  assert.match(table, /\.table\s*\{[\s\S]*min-inline-size:\s*100%/);
  assert.match(badge, /data-aven-badge=""/);
  assert.match(layout, /\[data-aven-badge\]\[data-variant\][\s\S]*max-inline-size:\s*100%[\s\S]*overflow-wrap:\s*anywhere[\s\S]*white-space:\s*normal/);
});

test("Light, Dark and System theme engine keeps resolved DOM state live and persistent", () => {
  const provider = read("components", "theme-provider.tsx");
  const rootLayout = read("app", "layout.tsx");

  assert.match(provider, /root\.dataset\.themePreference = preference/);
  assert.match(provider, /root\.dataset\.theme = resolved/);
  assert.match(provider, /root\.style\.colorScheme = resolved/);
  assert.match(provider, /theme !== "system"/);
  assert.match(provider, /media\.addEventListener\("change", handleSystemThemeChange\)/);
  assert.match(provider, /window\.addEventListener\("storage", handleStorage\)/);
  assert.match(rootLayout, /getThemeBootstrapScript\(\)/);
  assert.ok(rootLayout.indexOf("appearanceBootstrap") < rootLayout.indexOf("<body>"));
});

test("dropdowns and tooltips recalculate against visual viewport and stay viewport bounded", () => {
  const positioning = read("components", "ui", "viewport-position.ts");
  const dropdown = read("components", "ui", "dropdown.tsx");
  const overlays = read("components", "ui", "overlays.module.css");

  assert.match(positioning, /window\.visualViewport/);
  assert.match(positioning, /clampInlinePosition/);
  assert.match(positioning, /availableBelow/);
  assert.match(positioning, /availableAbove/);
  assert.match(dropdown, /window\.addEventListener\("resize", updatePosition\)/);
  assert.match(dropdown, /window\.addEventListener\("scroll", updatePosition, true\)/);
  assert.match(dropdown, /visualViewport\?\.addEventListener\("resize", updatePosition\)/);
  assert.match(overlays, /\.dropdownContent\s*\{[\s\S]*max-block-size:\s*calc\(100dvh - var\(--space-4\)\)[\s\S]*max-inline-size:\s*calc\(100vw - var\(--space-4\)\)/);
  assert.match(overlays, /\.dialog\s*\{[\s\S]*max-block-size:\s*calc\(100% - var\(--dialog-safe-margin\)\)/);
});
