import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (...parts) => fs.readFileSync(path.join(ROOT, ...parts), "utf8");

function cssBlock(source, selector) {
  const selectorIndex = source.indexOf(selector);
  assert.notEqual(selectorIndex, -1, `${selector} should exist`);

  const blockStart = source.indexOf("{", selectorIndex);
  const blockEnd = source.indexOf("}", blockStart);
  assert.notEqual(blockStart, -1, `${selector} should open a CSS block`);
  assert.notEqual(blockEnd, -1, `${selector} should close a CSS block`);

  return source.slice(blockStart + 1, blockEnd);
}

test("Application Shell is the single authority for sidebar/main horizontal geometry", () => {
  const shell = read("components", "app-shell", "app-shell.module.css");

  const shellBlock = cssBlock(shell, ".shell {");
  assert.match(
    shellBlock,
    /grid-template-columns:\s*var\(--shell-sidebar-inline-size\)\s+minmax\(0,\s*1fr\)/,
  );

  const collapsed = cssBlock(shell, ':global(html[data-sidebar="collapsed"]) .shell');
  assert.match(
    collapsed,
    /grid-template-columns:\s*var\(--shell-sidebar-collapsed-inline-size\)\s+minmax\(0,\s*1fr\)/,
  );

  for (const selector of [".workspace {", ".mainContent {", ".contentFrame {"]) {
    assert.match(cssBlock(shell, selector), /min-inline-size:\s*var\(--space-0\)/);
  }

  assert.doesNotMatch(shell, /calc\(\s*100vw\s*-\s*var\(--shell-sidebar/);
});

test("outer shell frame is fluid while PageContainer owns semantic max widths", () => {
  const layout = read("app", "layout-system.css");
  const outerFrame = cssBlock(layout, "#main-content > div {");

  assert.match(outerFrame, /box-sizing:\s*border-box/);
  assert.match(outerFrame, /inline-size:\s*100%/);
  assert.match(outerFrame, /max-inline-size:\s*100%/);
  assert.match(outerFrame, /min-inline-size:\s*0/);
  assert.doesNotMatch(outerFrame, /padding/);
  assert.doesNotMatch(outerFrame, /margin-inline/);
  assert.doesNotMatch(outerFrame, /--layout-page-max-inline-size-(?:standard|wide)/);

  assert.match(
    layout,
    /\[data-aven-page-container\]\[data-width="standard"\][\s\S]*max-inline-size:\s*var\(--layout-page-max-inline-size-standard\)/,
  );
  assert.match(
    layout,
    /\[data-aven-page-container\]\[data-width="wide"\][\s\S]*max-inline-size:\s*var\(--layout-page-max-inline-size-wide\)/,
  );
  assert.match(
    layout,
    /\[data-aven-page-container\]\[data-width="full"\][\s\S]*max-inline-size:\s*var\(--layout-page-max-inline-size-full\)/,
  );
});

test("responsive gutters stay owned by the shell and follow the shared token contract", () => {
  const shell = read("components", "app-shell", "app-shell.module.css");
  const layout = read("app", "layout-system.css");

  assert.match(
    cssBlock(shell, ".contentFrame {"),
    /padding:\s*var\(--space-6\)\s+var\(--shell-page-gutter\)\s+var\(--space-10\)/,
  );
  assert.match(layout, /--shell-page-gutter:\s*var\(--layout-page-padding-current\)/);
  assert.match(layout, /--shell-page-gutter-compact:\s*var\(--layout-page-padding-inline-compact\)/);
  assert.match(layout, /@media \(max-width: 80rem\)[\s\S]*--layout-page-padding-current:\s*var\(--layout-page-padding-inline-medium\)/);
  assert.match(layout, /@media \(max-width: 53\.125rem\)[\s\S]*--layout-page-padding-current:\s*var\(--layout-page-padding-inline-compact\)/);
});

test("main content keeps local scrolling without masking horizontal layout bugs", () => {
  const shell = read("components", "app-shell", "app-shell.module.css");
  const main = cssBlock(shell, ".mainContent {");

  assert.match(main, /overflow:\s*auto/);
  assert.doesNotMatch(main, /overflow-x:\s*hidden/);

  const layout = read("app", "layout-system.css");
  assert.doesNotMatch(layout, /#main-content[^}]*overflow-x:\s*hidden/s);
});

test("constrained and fluid page modes remain explicit instead of depending on sidebar width", () => {
  const component = read("components", "aven", "layout.tsx");
  const settings = read("app", "settings", "layout.tsx");

  assert.match(component, /export type PageWidth = "standard" \| "wide" \| "full"/);
  assert.match(component, /data-width=\{width\}/);
  assert.match(settings, /<PageContainer width="standard"/);

  for (const page of [
    ["app", "billing", "page.tsx"],
    ["app", "inventory", "page.tsx"],
  ]) {
    const source = read(...page);
    assert.doesNotMatch(source, /--shell-sidebar-inline-size|--shell-sidebar-collapsed-inline-size/);
    assert.doesNotMatch(source, /calc\(\s*100vw\s*-/);
  }
});
