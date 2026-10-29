import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Collections filter layout uses semantic sizing roles instead of expanding fields with equal fractions", async () => {
  const layout = await source("../app/collections/collections-layout.module.css");

  assert.match(layout, /--filter-field-default-inline-size/);
  assert.match(layout, /--filter-field-wide-inline-size/);
  assert.match(layout, /\.opportunity-filter\.account-filter/);
  assert.match(layout, /\.opportunity-filter-grid\)[\s\S]*display:\s*flex/);
  assert.doesNotMatch(layout, /\.opportunity-filter-grid\)[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)/);
  assert.doesNotMatch(layout, /min-inline-size:\s*56rem/);
});

test("Collection comparison and workspace density avoid historical fixed empty-state and diff widths", async () => {
  const styles = await source("../app/collections/collection.module.css");

  assert.match(styles, /\.baselinePicker[\s\S]*--filter-field-wide-inline-size/);
  assert.match(styles, /\.compareHeader[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto\s+minmax\(0,\s*1fr\)/);
  assert.doesNotMatch(styles, /45vh/);
  assert.doesNotMatch(styles, /min-inline-size:\s*16rem/);
});

test("Historical cycles consume official Aven filter and form primitives", async () => {
  const page = await source("../app/opportunities/history-cycles/page.tsx");

  for (const component of ["FilterBar", "FilterItem", "Alert", "Button", "Input", "Select"]) {
    assert.ok(page.includes(component), `expected ${component} in history cycles`);
  }

  assert.match(page, /<FilterItem size="wide">[\s\S]*id="history-cycle"/);
  assert.match(page, /id="history-provider"/);
  assert.match(page, /id="history-status"/);
  assert.match(page, /id="history-severity"/);
  assert.match(page, /id="history-search"/);
  assert.doesNotMatch(page, /style=\{\{\s*marginTop:/);
});

test("Historical cycles use semantic Aven surfaces and keep table overflow local", async () => {
  const styles = await source("../app/opportunities/history-cycles/page.module.css");

  assert.match(styles, /var\(--elevation-1-surface\)/);
  assert.match(styles, /var\(--border-subtle\)/);
  assert.match(styles, /\.tableScroll[\s\S]*overflow-x:\s*auto/);
  assert.match(styles, /\.table[\s\S]*min-inline-size:\s*100%/);
  assert.doesNotMatch(styles, /min-width:\s*980px/);
  assert.doesNotMatch(styles, /var\(--border\)/);
  assert.doesNotMatch(styles, /var\(--surface\)/);
  assert.doesNotMatch(styles, /var\(--muted\)/);
});

test("Task 24.27 touched visual files pass the Aven hardcode gate", async () => {
  const filenames = [
    "app/collections/collection.module.css",
    "app/collections/collections-layout.module.css",
    "app/opportunities/history-cycles/page.tsx",
    "app/opportunities/history-cycles/page.module.css",
  ];

  const entries = await Promise.all(
    filenames.map(async (filename) => [filename, await source(`../${filename}`)]),
  );
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));

  assert.deepEqual(summarize(violations), {
    colors: 0,
    spacing: 0,
    radius: 0,
    typography: 0,
  });
  assert.deepEqual(violations, []);
});
