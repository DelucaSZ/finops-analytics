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

test("Settings uses the full shell-provided inline size in every layout state", () => {
  const layout = read("app", "settings", "layout.tsx");
  const fullContainers = layout.match(/<PageContainer\s+(?:\n\s*)?width="full"/g) ?? [];

  assert.equal(fullContainers.length, 3);
  assert.doesNotMatch(layout, /width="standard"/);
  assert.doesNotMatch(layout, /--shell-sidebar-inline-size|--shell-sidebar-collapsed-inline-size/);
  assert.doesNotMatch(layout, /calc\(\s*100vw\s*-/);
});

test("Settings shared wrapper remains shrink-safe and fluid", () => {
  const styles = read("app", "settings", "settings-layout.module.css");

  for (const selector of [".page,", ".content {"]) {
    const block = cssBlock(styles, selector);
    assert.match(block, /width:\s*100%/);
  }

  assert.match(styles, /\.page > \*,[\s\S]*\.content > \*[\s\S]*min-inline-size:\s*0/);
});

test("Settings navigation owns horizontal overflow and keeps the active tab reachable", () => {
  const layout = read("app", "settings", "layout.tsx");
  const styles = read("app", "settings", "settings-layout.module.css");

  const viewport = cssBlock(styles, ".navigationViewport {");
  assert.match(viewport, /max-inline-size:\s*100%/);
  assert.match(viewport, /overflow-x:\s*auto/);
  assert.match(viewport, /overscroll-behavior-inline:\s*contain/);

  const tabs = cssBlock(styles, ".tabs {");
  assert.match(tabs, /inline-size:\s*max-content/);
  assert.match(tabs, /min-inline-size:\s*100%/);

  assert.match(layout, /navigationViewportRef/);
  assert.match(layout, /aria-selected="true"/);
  assert.match(layout, /scrollIntoView\(\{ block: "nearest", inline: "nearest" \}\)/);
});

test("Settings keeps forms readable while the page container expands", () => {
  const styles = read("app", "settings", "settings-layout.module.css");

  assert.match(
    styles,
    /\.content :global\(\.panel form\),[\s\S]*max-inline-size:\s*calc\(var\(--filter-field-wide-inline-size\) \+ var\(--filter-field-wide-inline-size\) \+ var\(--space-4\)\)/,
  );
  assert.match(
    styles,
    /\.content :global\(\.settings-form-grid\),[\s\S]*grid-template-columns:\s*repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(
    styles,
    /@media \(max-width: 62rem\)[\s\S]*grid-template-columns:\s*minmax\(0, 1fr\)/,
  );
});
