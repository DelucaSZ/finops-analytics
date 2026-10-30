import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

const layoutSystem = () => read("app", "layout-system.css");

test("root layout loads geometry after surface hierarchy", () => {
  const source = read("app", "layout.tsx");
  const surface = source.indexOf('import "./surface-hierarchy.css";');
  const layout = source.indexOf('import "./layout-system.css";');

  assert.ok(surface >= 0);
  assert.ok(layout > surface);
});

test("global layout tokens derive widths, gutters and rhythm from the Aven spacing scale", () => {
  const source = layoutSystem();

  for (const token of [
    "--layout-page-max-inline-size-standard",
    "--layout-page-max-inline-size-wide",
    "--layout-page-max-inline-size-full",
    "--layout-page-padding-inline",
    "--layout-page-padding-inline-medium",
    "--layout-page-padding-inline-compact",
    "--layout-page-gap",
    "--layout-section-gap",
    "--layout-component-gap",
    "--layout-grid-gap",
    "--layout-grid-columns-1",
    "--layout-grid-columns-2",
    "--layout-grid-columns-3",
    "--layout-grid-columns-4",
    "--layout-grid-columns-5",
  ]) assert.match(source, new RegExp(token));

  assert.match(source, /--layout-page-gap:\s*var\(--space-6\)/);
  assert.match(source, /--layout-section-gap:\s*var\(--space-5\)/);
  assert.match(source, /--layout-component-gap:\s*var\(--space-4\)/);
  assert.match(source, /--layout-grid-gap:\s*var\(--space-4\)/);
  assert.match(source, /--shell-page-gutter:\s*var\(--layout-page-padding-current\)/);
});

test("shell content frame stays fluid while Application Shell owns responsive padding", () => {
  const source = layoutSystem();
  const frame = source.match(/#main-content > div \{[\s\S]*?\n\}/)?.[0] ?? "";
  const shell = read("components", "app-shell", "app-shell.module.css");
  const contentFrame = shell.match(/\.contentFrame \{[\s\S]*?\n\}/)?.[0] ?? "";

  assert.match(frame, /box-sizing:\s*border-box/);
  assert.match(frame, /inline-size:\s*100%/);
  assert.match(frame, /max-inline-size:\s*100%/);
  assert.match(frame, /min-inline-size:\s*0/);
  assert.doesNotMatch(frame, /margin-inline|padding|--layout-page-max-inline-size-(?:standard|wide)/);
  assert.doesNotMatch(frame, /sidebar|--shell-sidebar/);
  assert.match(contentFrame, /padding:\s*var\(--space-6\)\s+var\(--shell-page-gutter\)\s+var\(--space-10\)/);
  assert.match(source, /@media \(max-width: 80rem\)[\s\S]*--layout-page-padding-current:\s*var\(--layout-page-padding-inline-medium\)/);
  assert.match(source, /@media \(max-width: 53\.125rem\)[\s\S]*--layout-page-padding-current:\s*var\(--layout-page-padding-inline-compact\)/);
});

test("Aven exposes semantic PageContainer Stack Cluster and Grid primitives", () => {
  const source = read("components", "aven", "layout.tsx");

  assert.match(source, /export type PageWidth = "standard" \| "wide" \| "full"/);
  assert.match(source, /export function PageContainer/);
  assert.match(source, /data-aven-page-container/);
  assert.match(source, /export function Stack/);
  assert.match(source, /data-aven-stack/);
  assert.match(source, /export function Cluster/);
  assert.match(source, /data-aven-cluster/);
  assert.match(source, /export type GridVariant = "auto" \| "metrics" \| "content" \| "split"/);
  assert.match(source, /data-aven-grid=\{variant\}/);
  assert.match(source, /data-aven-page-header/);
  assert.match(source, /data-aven-section/);
});

test("layout primitives use flexible minmax and auto-fit grids with structural wrapping", () => {
  const source = layoutSystem();

  assert.match(source, /\[data-aven-cluster\][\s\S]*flex-wrap:\s*wrap/);
  assert.match(source, /\[data-aven-grid="metrics"\][\s\S]*auto-fit[\s\S]*minmax/);
  assert.match(source, /\[data-aven-grid="content"\][\s\S]*auto-fit[\s\S]*minmax/);
  assert.match(source, /\[data-aven-grid="split"\][\s\S]*var\(--layout-grid-columns-split\)/);
  assert.match(source, /@media \(max-width: 62rem\)[\s\S]*\[data-aven-grid="split"\][\s\S]*var\(--layout-grid-columns-1\)/);
});

test("target analytical pages share page rhythm and grid contracts", () => {
  const pages = [
    ["components", "executive-dashboard.module.css"],
    ["app", "billing", "billing.module.css"],
    ["app", "inventory", "inventory.module.css"],
    ["app", "opportunities", "opportunities.module.css"],
    ["app", "rds", "reservations", "rds-reservations.module.css"],
  ];

  for (const parts of pages) {
    const source = read(...parts);
    assert.match(source, /gap:\s*var\(--layout-page-gap\)/, `${parts.join("/")} must use page rhythm`);
    assert.match(source, /gap:\s*var\(--layout-grid-gap\)/, `${parts.join("/")} must use shared grid gap`);
    assert.match(source, /grid-template-columns:\s*var\(--layout-grid-columns-/, `${parts.join("/")} must use shared grid columns`);
  }
});

test("Settings explicitly opts into the fluid autofit width", () => {
  const source = read("app", "settings", "layout.tsx");
  assert.match(source, /PageContainer, PageHeader/);
  assert.ok((source.match(/<PageContainer/g) ?? []).length >= 3);
  assert.match(source, /<PageContainer width="full" className=\{styles\.page\}>/);
});

test("PageHeader keeps actions wrapping structurally on narrow viewports", () => {
  const source = read("components", "aven", "product-components.module.css");
  assert.match(source, /\.pageHeaderMain,[\s\S]*flex-wrap:\s*wrap/);
  assert.match(source, /@media \(max-width: 48rem\)[\s\S]*\.pageActions,[\s\S]*inline-size:\s*100%/);
  assert.match(source, /@media \(max-width: 48rem\)[\s\S]*\.pageActions,[\s\S]*justify-content:\s*flex-start/);
});

test("layout layer does not absorb FilterBar or table responsibilities", () => {
  const source = layoutSystem();
  assert.doesNotMatch(source, /FilterBar|filter-field|table-cell|sticky-column|row-action/i);
});

test("global layout layer passes the Aven hardcode gate", () => {
  const target = path.join(ROOT, "app", "layout-system.css");
  const violations = scanDirectory(target);
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
});
