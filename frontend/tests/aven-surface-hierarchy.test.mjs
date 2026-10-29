import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const frontendUrl = new URL("../", import.meta.url);
const appUrl = new URL("app/", frontendUrl);
const tokenUrl = new URL("app/styles/tokens/", frontendUrl);
const uiUrl = new URL("components/ui/", frontendUrl);

const read = (url) => readFile(url, "utf8");

test("light and dark themes expose one semantic surface hierarchy", async () => {
  const [light, dark] = await Promise.all([
    read(new URL("semantic-light.css", tokenUrl)),
    read(new URL("semantic-dark.css", tokenUrl)),
  ]);

  for (const token of [
    "--surface-canvas",
    "--surface-page",
    "--surface-section",
    "--surface-panel",
    "--surface-card",
    "--surface-elevated",
    "--surface-interactive",
    "--surface-hover",
    "--surface-selected",
    "--surface-overlay",
  ]) {
    assert.ok(light.includes(`${token}:`), `light theme is missing ${token}`);
    assert.ok(dark.includes(`${token}:`), `dark theme is missing ${token}`);
  }

  assert.match(light, /--surface-canvas:\s*var\(--application-background\)/);
  assert.match(dark, /--surface-canvas:\s*var\(--application-background\)/);
  assert.match(light, /--surface-page:\s*var\(--page-background\)/);
  assert.match(dark, /--surface-page:\s*var\(--page-background\)/);
});

test("component tokens map sections, panels, cards, filters and tables to semantic surfaces", async () => {
  const components = await read(new URL("components.css", tokenUrl));

  for (const contract of [
    "--section-background: var(--surface-section);",
    "--panel-background: var(--surface-panel);",
    "--card-background: var(--surface-card);",
    "--interactive-surface-background: var(--surface-interactive);",
    "--filter-background: var(--surface-section);",
    "--table-background: var(--surface-panel);",
    "--table-header-background: var(--surface-card);",
    "--table-row-hover-background: var(--surface-hover);",
    "--table-row-selected-background: var(--surface-selected);",
  ]) {
    assert.ok(components.includes(contract), `missing surface contract ${contract}`);
  }
});

test("Surface primitive exposes semantic variants instead of visual opacity props", async () => {
  const [surface, index, card, table, productLayout] = await Promise.all([
    read(new URL("surface.tsx", uiUrl)),
    read(new URL("index.ts", uiUrl)),
    read(new URL("card.tsx", uiUrl)),
    read(new URL("table.tsx", uiUrl)),
    read(new URL("components/aven/layout.tsx", frontendUrl)),
  ]);

  assert.match(surface, /"section" \| "panel" \| "card" \| "elevated" \| "interactive"/);
  assert.doesNotMatch(surface, /opacity\??:|background\??:|borderColor\??:/);
  assert.match(surface, /data-aven-surface=\{variant\}/);
  assert.ok(index.includes('export * from "./surface";'));
  assert.ok(card.includes('data-aven-surface="card"'));
  assert.ok(table.includes("data-aven-table"));
  assert.ok(productLayout.includes('<Surface as="section" variant="section"'));
  assert.ok(productLayout.includes('<Surface variant="panel"'));
});

test("global hierarchy layer is loaded last and contains no local color or glassmorphism hacks", async () => {
  const [layout, hierarchy] = await Promise.all([
    read(new URL("layout.tsx", appUrl)),
    read(new URL("surface-hierarchy.css", appUrl)),
  ]);

  const compatibilityImport = layout.indexOf('import "./legacy-theme-compat.css";');
  const hierarchyImport = layout.indexOf('import "./surface-hierarchy.css";');
  assert.ok(compatibilityImport >= 0 && hierarchyImport > compatibilityImport);
  assert.doesNotMatch(hierarchy, /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i);
  assert.doesNotMatch(hierarchy, /backdrop-filter|filter:\s*blur|glow/i);
  assert.match(hierarchy, /background:\s*var\(--panel-background\)/);
  assert.match(hierarchy, /background:\s*var\(--table-row-hover-background\)/);
});
