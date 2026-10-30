import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

function block(sourceText, selectorPattern) {
  const match = sourceText.match(new RegExp(`${selectorPattern}\\s*\\{([^}]*)\\}`, "s"));
  assert.ok(match, `expected CSS block matching ${selectorPattern}`);
  return match[1];
}

test("Collections filter layout uses an adaptive semantic grid instead of fixed page width", async () => {
  const layout = await source("../app/collections/collections-layout.module.css");
  const filterGrid = block(layout, "\\.scope :global\\(\\.opportunity-filter-grid\\)");
  const accountFilter = block(layout, "\\.scope :global\\(\\.opportunity-filter\\.account-filter\\)");

  assert.match(layout, /--filter-field-min-inline-size/);
  assert.match(layout, /\.opportunity-filter\.account-filter/);
  assert.match(filterGrid, /display:\s*grid/);
  assert.match(filterGrid, /grid-template-columns:\s*repeat\(/);
  assert.match(filterGrid, /auto-fit/);
  assert.match(filterGrid, /--filter-field-min-inline-size/);
  assert.match(accountFilter, /grid-column:\s*span 2/);
  assert.doesNotMatch(filterGrid, /display:\s*flex/);
  assert.doesNotMatch(layout, /min-inline-size:\s*56rem/);
});

test("Collection filters consume Aven form primitives while preserving datetime query semantics", async () => {
  const workspace = await source("../components/collection-workspace.tsx");

  for (const component of ["Button", "Input", "Select"]) {
    assert.ok(workspace.includes(component), `expected ${component} in CollectionWorkspace`);
  }

  assert.match(workspace, /label="Cloud"/);
  assert.match(workspace, /label="Conta · nome ou identificador"/);
  assert.match(workspace, /label="Status"/);
  assert.match(workspace, /type="datetime-local"[\s\S]*label="Início do período \(inclusivo\)"/);
  assert.match(workspace, /type="datetime-local"[\s\S]*label="Fim do período \(exclusivo\)"/);
  assert.match(workspace, /new Date\(event\.target\.value\)\.toISOString\(\)/);
  assert.doesNotMatch(workspace, /<input\b/);
});

test("Collection scheduling uses shared Aven controls without changing schedule semantics", async () => {
  const schedule = await source("../components/collection-schedule-fields.tsx");

  assert.match(schedule, /import \{ Checkbox, Select \} from "@\/components\/ui"/);
  assert.match(schedule, /checked=\{scheduleEnabled\}/);
  assert.match(schedule, /onScheduleEnabledChange\(event\.target\.checked\)/);
  assert.match(schedule, /value=\{String\(scanIntervalHours\)\}/);
  assert.match(schedule, /onIntervalChange\(Number\(event\.target\.value\)\)/);
  assert.match(schedule, /formatDate\(nextScanAt\)/);
  assert.doesNotMatch(schedule, /<input\b|<select\b/);
});

test("Collection comparison and workspace density avoid historical fixed empty-state and diff widths", async () => {
  const styles = await source("../app/collections/collection.module.css");
  const compareHeader = block(styles, "\\.compareHeader");

  assert.match(styles, /\.baselinePicker[\s\S]*--filter-field-wide-inline-size/);
  assert.match(compareHeader, /grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto\s+minmax\(0,\s*1fr\)/);
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

test("Historical cycles use shared Aven surfaces and the shared analytical table overflow contract", async () => {
  const page = await source("../app/opportunities/history-cycles/page.tsx");
  const styles = await source("../app/opportunities/history-cycles/page.module.css");
  const tableStyles = await source("../components/ui/table.module.css");
  const tableWrapper = block(tableStyles, "\\.tableWrapper");
  const table = block(tableStyles, "\\.table");

  assert.match(page, /<Section/);
  assert.match(page, /<MetricCard/);
  assert.match(page, /<Table density="compact"/);
  assert.match(page, /<TableState state="empty"/);
  assert.doesNotMatch(page, /<table\b/);
  assert.doesNotMatch(styles, /\.tableScroll\b|\.tableCard\b/);
  assert.match(styles, /var\(--border-subtle\)/);
  assert.match(tableWrapper, /overflow-x:\s*auto/);
  assert.match(table, /min-inline-size:\s*100%/);
  assert.doesNotMatch(styles, /min-width:\s*980px/);
  assert.doesNotMatch(styles, /var\(--border\)/);
  assert.doesNotMatch(styles, /var\(--surface\)/);
  assert.doesNotMatch(styles, /var\(--muted\)/);
});

test("Task 24.27 touched visual files pass the Aven hardcode gate", async () => {
  const filenames = [
    "components/collection-workspace.tsx",
    "components/collection-schedule-fields.tsx",
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
