import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Billing keeps the approved compact row outside custom period mode", async () => {
  const page = await source("../app/billing/page.tsx");

  assert.ok(page.includes('const periodPicker = ('));
  assert.ok(page.includes('{periodPreset !== "custom" && periodPicker}'));
  assert.ok(page.includes('clearable={periodPreset === "custom"}'));
  assert.ok(page.includes('layout={periodPreset === "custom" ? "inline" : undefined}'));
});

test("Billing moves the custom period controls into the FilterBar secondary row", async () => {
  const page = await source("../app/billing/page.tsx");

  assert.ok(page.includes('secondary={periodPreset === "custom" ? ('));
  assert.ok(page.includes('<FilterItem size="fluid">{periodPicker}</FilterItem>'));

  const filterStart = page.indexOf('<FilterBar');
  const filterEnd = page.indexOf('</FilterBar>', filterStart);
  const filterSource = page.slice(filterStart, filterEnd);
  const profileIndex = filterSource.indexOf('label="Perfil"');
  const metricIndex = filterSource.indexOf('label="Métrica"');
  const granularityIndex = filterSource.indexOf('label="Granularidade"');
  const groupingIndex = filterSource.indexOf('label="Agrupamento"');

  assert.ok(profileIndex >= 0);
  assert.ok(profileIndex < metricIndex);
  assert.ok(metricIndex < granularityIndex);
  assert.ok(granularityIndex < groupingIndex);
});

test("DateRangePicker inline mode aligns period, dates and clear action without visual hardcodes", async () => {
  const picker = await source("../components/aven/date-range-picker.tsx");
  const css = await source("../components/aven/product-components.module.css");

  assert.ok(picker.includes('layout?: "stacked" | "inline";'));
  assert.ok(picker.includes('layout = "stacked"'));
  assert.ok(picker.includes('data-layout={layout}'));

  assert.match(css, /\.dateRangePicker\[data-layout="inline"\]\s*\{[\s\S]*?align-items:\s*end;/);
  assert.match(css, /\.dateRangePicker\[data-layout="inline"\]\s*\{[\s\S]*?gap:\s*var\(--filter-grid-gap\);/);
  assert.match(css, /\.dateRangePicker\[data-layout="inline"\]\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4, minmax\(0, 1fr\)\);/);
  assert.match(css, /\.dateRangePicker\[data-layout="inline"\] \.dateRangeFields\s*\{[\s\S]*?display:\s*contents;/);
  assert.match(css, /\.dateRangePicker\[data-layout="inline"\] \.dateRangeActions\s*\{[\s\S]*?justify-content:\s*flex-start;/);
  assert.doesNotMatch(css, /\.dateRangePicker\[data-layout="inline"\][^}]*position:\s*absolute;/s);
});

test("Custom period layout follows the page container and collapses safely on narrow widths", async () => {
  const css = await source("../components/aven/product-components.module.css");

  assert.match(css, /@container aven-page \(max-width: 48rem\)[\s\S]*?\.dateRangePicker\[data-layout="inline"\][\s\S]*?grid-template-columns:\s*1fr;/);
  assert.match(css, /@media \(max-width: 48rem\)[\s\S]*?\.dateRangePicker\[data-layout="inline"\][\s\S]*?grid-template-columns:\s*1fr;/);
});

test("Billing preserves custom date behavior and clear semantics", async () => {
  const page = await source("../app/billing/page.tsx");
  const picker = await source("../components/aven/date-range-picker.tsx");

  assert.ok(page.includes('setPeriodPreset("custom");'));
  assert.ok(page.includes('setCustomFrom(value.startDate || "");'));
  assert.ok(page.includes('setCustomTo(value.endDate || "");'));
  assert.ok(page.includes('maxDate={today}'));
  assert.ok(picker.includes('onChange({ startDate: null, endDate: null });'));
  assert.ok(picker.includes('type="date"'));
  assert.ok(picker.includes('max={earlierDate(value.endDate, maxDate)}'));
  assert.ok(picker.includes('min={laterDate(value.startDate, minDate)}'));
});
