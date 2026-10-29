import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Billing composes the official Aven analytical component stack", async () => {
  const page = await source("../app/billing/page.tsx");

  for (const component of [
    "PageHeader",
    "Section",
    "AccountSelector",
    "FilterBar",
    "DateRangePicker",
    "MetricCard",
    "CurrencyDisplay",
    "PercentageDisplay",
    "StatusIndicator",
    "ProviderBadge",
    "ChartCard",
    "DataState",
    "Table",
    "Alert",
    "EmptyState",
  ]) {
    assert.ok(page.includes(component), `expected ${component} in Billing`);
  }

  assert.ok(!page.includes('@/components/page-header'));
  assert.ok(!page.includes('className="button'));
  assert.ok(!page.includes('className="panel'));
});

test("Billing starts from an explicit empty account contract and does not query before selection", async () => {
  const page = await source("../app/billing/page.tsx");

  assert.ok(page.includes("const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([]);"));
  assert.ok(page.includes("!hasBillingAccountSelection(selectedAccountIds)"));
  assert.ok(page.includes("setSummary(sectionState());"));
  assert.ok(page.includes("return;"));
  assert.ok(page.includes("selectAll"));
  assert.ok(page.includes('selectAllLabel="Selecionar todas"'));
  assert.ok(page.includes('clearLabel="Limpar seleção"'));
  assert.ok(page.includes("Nenhuma consulta ao Cost Explorer é executada enquanto a seleção estiver vazia."));
  assert.ok(!page.includes("selectedAccountIds.length === 0 ? accounts"));
});

test("Billing AccountSelector is compact by default and opens an Aven checkbox dropdown on demand", async () => {
  const selector = await source("../components/aven/selectors.tsx");
  const css = await source("../components/aven/product-components.module.css");

  assert.ok(selector.includes("<DropdownMenu"));
  assert.ok(selector.includes("<DropdownMenuTrigger"));
  assert.ok(selector.includes("<DropdownMenuContent"));
  assert.ok(selector.includes("<Checkbox"));
  assert.ok(selector.includes("indeterminate={partiallySelected}"));
  assert.ok(selector.includes('placeholder={props.placeholder ?? "Nenhuma conta selecionada"}'));
  assert.ok(selector.includes('return "Todas as contas selecionadas"'));
  assert.ok(selector.includes('return "1 conta selecionada"'));
  assert.ok(selector.includes("contas selecionadas"));
  assert.ok(!selector.includes("multiple={selection.multiple}"));
  assert.ok(!selector.includes("styles.multiSelect"));
  assert.match(css, /\.selectorTrigger\s*\{[\s\S]*?block-size:\s*var\(--control-height-compact\)/);
});

test("Billing AccountSelector keeps search, select-all and large-account scrolling inside the dropdown", async () => {
  const selector = await source("../components/aven/selectors.tsx");
  const css = await source("../components/aven/product-components.module.css");
  const dropdownStart = selector.indexOf("<DropdownMenuContent");
  const dropdownSource = selector.slice(dropdownStart);

  assert.ok(dropdownStart >= 0);
  assert.ok(dropdownSource.includes("searchPlaceholder"));
  assert.ok(dropdownSource.includes("selectorSelectAll"));
  assert.ok(dropdownSource.includes("selectorOptionList"));
  assert.ok(dropdownSource.includes("selection.value.includes(option.value)"));
  assert.ok(css.includes(".selectorOptionList"));
  assert.match(css, /\.selectorOptionList\s*\{[\s\S]*?overflow-y:\s*auto/);
  assert.match(css, /\.selectorDropdown\s*\{[\s\S]*?max-block-size:/);
});

test("Billing filters remain below account context and custom dates use DateRangePicker", async () => {
  const page = await source("../app/billing/page.tsx");
  const picker = await source("../components/aven/date-range-picker.tsx");

  assert.ok(page.indexOf('title="Contas"') < page.indexOf('title="Filtros"'));
  assert.ok(page.includes("<FilterBar"));
  assert.ok(page.includes("<DateRangePicker"));
  assert.ok(page.includes("periodPreset === \"custom\""));
  assert.ok(page.includes("maxDate={today}"));
  assert.ok(picker.includes('type="date"'));
  assert.ok(picker.includes("max={maxDate}"));
});

test("Billing DateRangePicker keeps preset mode compact and reveals dates only for custom input", async () => {
  const picker = await source("../components/aven/date-range-picker.tsx");
  const css = await source("../components/aven/product-components.module.css");

  assert.ok(picker.includes('activePreset === "custom"'));
  assert.ok(picker.includes('data-date-fields={dateFieldsVisible ? "visible" : "hidden"}'));
  assert.ok(picker.includes("{dateFieldsVisible && ("));
  assert.ok(picker.includes("{clearable && dateFieldsVisible && ("));
  assert.ok(css.includes('.dateRangePicker[data-date-fields="hidden"] .dateRangeFields'));
  assert.ok(css.includes('.filterPrimary > .dateRangePicker[data-date-fields="visible"]'));
});

test("Billing layout constrains account controls and reduces profile metadata to a compact contextual row", async () => {
  const css = await source("../app/billing/billing.module.css");

  assert.match(css, /\.accountContext\s*\{[\s\S]*?inline-size:\s*min\(100%, var\(--filter-field-wide-inline-size\)\)/);
  assert.match(css, /\.profileContext\s*\{[\s\S]*?border-block-start:\s*1px solid var\(--border-subtle\)/);
  assert.doesNotMatch(css, /\.profileContext\s*\{[^}]*background:/s);
  assert.doesNotMatch(css, /\.profileContext\s*\{[^}]*border-radius:/s);
  assert.match(css, /\.queryMetadata\s*\{[\s\S]*?border-block-start:/);
});

test("Billing financial presentation uses centralized currency and table primitives", async () => {
  const page = await source("../app/billing/page.tsx");

  assert.ok(page.includes("<CurrencyDisplay"));
  assert.ok(page.includes("<PercentageDisplay"));
  assert.ok(page.includes("<Table>"));
  assert.ok(page.includes("<TableHeader>"));
  assert.ok(page.includes("<TableBody>"));
  assert.ok(page.includes("<TableHead numeric>"));
  assert.ok(page.includes("<TableCell numeric>"));
  assert.ok(!page.includes("formatBillingMoney("));
});

test("Billing chart is tokenized, stacked and distinguishes actual forecast and estimated buckets", async () => {
  const chart = await source("../app/billing/billing-cost-chart.tsx");

  assert.ok(chart.includes("period.series.map"));
  assert.ok(chart.includes("positiveBase"));
  assert.ok(chart.includes("negativeBase"));
  assert.ok(chart.includes("var(--chart-series-1)"));
  assert.ok(chart.includes("var(--chart-forecast)"));
  assert.ok(chart.includes("billingStatusHasForecast(item.status)"));
  assert.ok(chart.includes("statusMarker(period.status)"));
  assert.ok(chart.includes("tabIndex={0}"));
  assert.ok(chart.includes("PercentageDisplay"));
});

test("Billing theme changes remain presentation-only and cannot enter query signatures", async () => {
  const page = await source("../app/billing/page.tsx");
  const chart = await source("../app/billing/billing-cost-chart.tsx");

  assert.ok(!page.includes("useTheme("));
  assert.ok(!chart.includes("useTheme("));
  assert.ok(!page.includes("resolvedTheme"));
  assert.ok(!chart.includes("resolvedTheme"));
  assert.ok(page.includes("billingQuerySignature"));
});

test("Billing page does not take scroll ownership from the Application Shell", async () => {
  const css = await source("../app/billing/billing.module.css");

  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.ok(!css.includes("overflow-x: auto"));
  assert.match(css, /\.page,[\s\S]*?min-inline-size:\s*0;/);
});

test("Billing files pass the Aven hardcode gate independently", async () => {
  const entries = [
    ["app/billing/page.tsx", await source("../app/billing/page.tsx")],
    ["app/billing/billing-cost-chart.tsx", await source("../app/billing/billing-cost-chart.tsx")],
    ["app/billing/billing.module.css", await source("../app/billing/billing.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  const summary = summarize(violations);

  assert.deepEqual(summary, {
    colors: 0,
    spacing: 0,
    radius: 0,
    typography: 0,
  });
  assert.deepEqual(violations, []);
});

test("Billing documentation records the critical analytical contracts", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_BILLING.md", import.meta.url), "utf8");

  assert.ok(docs.includes("[] accounts != all accounts"));
  assert.ok(docs.includes("No accounts selected"));
  assert.ok(docs.includes("No Cost Explorer query"));
  assert.ok(docs.includes("Estimated styling"));
  assert.ok(docs.includes("High-density analytical reference"));
});
