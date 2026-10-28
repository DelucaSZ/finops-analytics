import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function read(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

function block(source, selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = source.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "s"));
  assert.ok(match, `Expected ${selector} block`);
  return match[1];
}

test("Application Shell keeps one page scroll owner and does not override shared overlay placement", () => {
  const source = read("components/app-shell/app-shell.module.css");

  assert.match(block(source, ".shell"), /overflow:\s*hidden/);
  assert.match(block(source, ".mainContent"), /overflow:\s*auto/);
  assert.match(block(source, ".navigation"), /overflow-y:\s*auto/);
  assert.match(block(source, ".contentFrame > *"), /min-inline-size:\s*var\(--space-0\)/);
  assert.doesNotMatch(source, /\.themeMenu,\s*\.userMenu\s*\{[^}]*transform:/s);
});

test("Dropdown and Tooltip share viewport-aware collision positioning", () => {
  const positioning = read("components/ui/viewport-position.ts");
  const dropdown = read("components/ui/dropdown.tsx");
  const tooltip = read("components/ui/tooltip.tsx");
  const overlays = read("components/ui/overlays.module.css");

  assert.match(positioning, /--space-2/);
  assert.match(positioning, /window\.innerWidth/);
  assert.match(positioning, /window\.innerHeight/);
  assert.match(positioning, /side:\s*"top"\s*\|\s*"bottom"/);
  assert.match(dropdown, /positionDropdown/);
  assert.match(dropdown, /maxBlockSize:\s*position\.maxBlockSize/);
  assert.match(tooltip, /positionTooltip/);
  assert.match(block(overlays, ".dropdownContent"), /overflow-y:\s*auto/);
  assert.match(block(overlays, ".dropdownContent"), /max-inline-size:\s*calc\(100vw - var\(--space-4\)\)/);
  assert.match(block(overlays, ".tooltipContent"), /max-inline-size:\s*min\(/);
});

test("shared Aven product components own narrow header, filter and metric behavior", () => {
  const source = read("components/aven/product-components.module.css");

  assert.match(block(source, ".pageHeader"), /min-inline-size:\s*0/);
  assert.match(block(source, ".metricCard"), /block-size:\s*100%/);
  assert.match(source, /@media \(max-width:\s*48rem\)/);
  assert.match(source, /\.pageHeaderMain,[\s\S]*\.filterBar\s*\{[\s\S]*flex-direction:\s*column/);
  assert.match(source, /\.filterPrimary > \*\s*\{[^}]*max-inline-size:\s*100%/s);
});

test("Aven pages use the shared composition scale instead of historical page-specific breakpoints", () => {
  const files = [
    "app/rds/reservations/rds-reservations.module.css",
    "app/inventory/inventory.module.css",
    "app/opportunities/opportunities.module.css",
    "app/flow/flow-layout.module.css",
    "app/settings/settings-layout.module.css",
  ];

  for (const file of files) {
    const source = read(file);
    assert.doesNotMatch(source, /@media \(max-width:\s*(1279|1100|900|760|700|640)px\)/, file);
    assert.match(source, /@media \(max-width:\s*(78|62|48)rem\)/, file);
  }

  assert.match(read("app/rds/reservations/rds-reservations.module.css"), /@media \(max-width:\s*78rem\)/);
  assert.match(read("app/flow/flow-layout.module.css"), /@media \(max-width:\s*62rem\)/);
  assert.match(read("app/settings/settings-layout.module.css"), /@media \(max-width:\s*48rem\)/);
});

test("primary Aven pages share the same outer page rhythm", () => {
  const sources = [
    read("components/executive-dashboard.module.css"),
    read("app/billing/billing.module.css"),
    read("app/rds/reservations/rds-reservations.module.css"),
    read("app/inventory/inventory.module.css"),
    read("app/opportunities/opportunities.module.css"),
    read("app/flow/flow-layout.module.css"),
    read("app/settings/settings-layout.module.css"),
  ];

  for (const source of sources) {
    assert.match(block(source, ".page"), /gap:\s*var\(--space-6\)/);
  }
});

test("table primitive keeps horizontal overflow inside the table container", () => {
  const source = read("components/ui/feedback.module.css");
  const wrapper = block(source, ".tableWrapper");

  assert.match(wrapper, /overflow:\s*auto/);
  assert.match(wrapper, /inline-size:\s*100%/);
});
