import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const AVEN = path.join(ROOT, "components", "aven");
const UI = path.join(ROOT, "components", "ui");
const read = (name) => fs.readFileSync(path.join(AVEN, name), "utf8");

const requiredFiles = [
  "types.ts",
  "displays.tsx",
  "resource-identifier.tsx",
  "data-state.tsx",
  "layout.tsx",
  "metric-card.tsx",
  "selectors.tsx",
  "date-range-picker.tsx",
  "recommendation-card.tsx",
  "product-components.module.css",
  "index.ts",
];

test("Aven Product Components expose the required layer", () => {
  for (const file of requiredFiles) assert.ok(fs.existsSync(path.join(AVEN, file)), `${file} should exist`);
  const barrel = read("index.ts");
  for (const stem of ["types", "displays", "resource-identifier", "data-state", "layout", "metric-card", "selectors", "date-range-picker", "recommendation-card"]) {
    assert.match(barrel, new RegExp(`\\./${stem}`), `${stem} should be barrel-exported`);
  }
});

test("hardcode gate is zero for components/aven", () => {
  const summary = summarize(scanDirectory(AVEN));
  assert.deepEqual(summary, { colors: 0, spacing: 0, radius: 0, typography: 0 });
});

test("UI primitives never depend on product components", () => {
  const uiFiles = fs.readdirSync(UI).filter((file) => /\.(?:ts|tsx)$/.test(file));
  const source = uiFiles.map((file) => fs.readFileSync(path.join(UI, file), "utf8")).join("\n");
  assert.doesNotMatch(source, /components\/aven|@\/components\/aven/);
});

test("MetricCard differentiates null data from numeric zero and reuses Skeleton", () => {
  const source = read("metric-card.tsx");
  assert.match(source, /value == null \? emptyValue : value/);
  assert.match(source, /<Skeleton/);
  assert.match(source, /TrendIndicator/);
});

test("CurrencyDisplay requires explicit currency and uses Intl.NumberFormat", () => {
  const source = read("displays.tsx");
  assert.match(source, /currency: string/);
  assert.match(source, /style: "currency"/);
  assert.match(source, /new Intl\.NumberFormat/);
  assert.doesNotMatch(source, /provider.*currency|currency.*provider/i);
});

test("PercentageDisplay documents an explicit percent versus fraction input contract", () => {
  const source = read("displays.tsx");
  assert.match(source, /valueMode\?: "percent" \| "fraction"/);
  assert.match(source, /valueMode === "percent" \? value \/ 100 : value/);
  assert.match(source, /style: "percent"/);
});

test("Trend direction and sentiment are independent contracts", () => {
  const source = read("displays.tsx");
  assert.match(source, /const trendIcons/);
  assert.match(source, /const trendVariants/);
  assert.match(source, /positive: "success"/);
  assert.match(source, /negative: "danger"/);
  assert.match(source, /flat: Minus/);
});

test("selectors support single, multi, search, clear, localized actions, and explicit select-all without implicit all", () => {
  const source = read("selectors.tsx");
  assert.match(source, /multiple\?: false/);
  assert.match(source, /multiple: true/);
  assert.match(source, /searchable/);
  assert.match(source, /selection\.onChange\(\[\]\)/);
  assert.match(source, /selectAllLabel = "Select all"/);
  assert.match(source, /clearLabel = "Clear"/);
  assert.match(source, /\{selectAllLabel\}/);
  assert.match(source, /\{clearLabel\}/);
  assert.doesNotMatch(source, /value\.length === 0.*all/i);
});

test("DateRangePicker uses viewport-managed native date inputs and caller-configured presets", () => {
  const source = read("date-range-picker.tsx");
  assert.match(source, /type="date"/);
  assert.match(source, /presets\.map/);
  assert.match(source, /startDate: null, endDate: null/);
  assert.match(source, /maxDate\?: string/);
  assert.match(source, /presetPlaceholder\?: string/);
  assert.doesNotMatch(source, /createPortal|position:\s*absolute/);
});

test("RecommendationCard stays presentational", () => {
  const source = read("recommendation-card.tsx");
  assert.match(source, /potentialSavings/);
  assert.match(source, /confidence/);
  assert.match(source, /actions/);
  assert.doesNotMatch(source, /fetch\(|useApiQuery|router\./);
});

test("DataState owns presentation only", () => {
  const source = read("data-state.tsx");
  assert.match(source, /<Alert/);
  assert.match(source, /<EmptyState/);
  assert.match(source, /<Skeleton/);
  assert.doesNotMatch(source, /fetch\(|useEffect|retry\(/);
});

test("technical preview includes every required product component", () => {
  const preview = fs.readFileSync(path.join(ROOT, "app", "dev", "ui", "page.tsx"), "utf8");
  for (const component of [
    "PageHeader", "Section", "MetricCard", "FilterBar", "AccountSelector", "EnvironmentSelector", "ProviderSelector",
    "DateRangePicker", "ChartCard", "StatusIndicator", "ProviderBadge", "ResourceIdentifier", "CurrencyDisplay",
    "PercentageDisplay", "TrendIndicator", "RecommendationCard", "DataState",
  ]) assert.match(preview, new RegExp(component));
});
