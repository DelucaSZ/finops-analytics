import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const COMPONENTS = path.join(ROOT, "components");
const APP = path.join(ROOT, "app");
const DOCS = path.resolve(ROOT, "..", "docs", "brand", "aven");
const DASHBOARD = path.join(COMPONENTS, "executive-dashboard.tsx");
const DASHBOARD_STYLES = path.join(COMPONENTS, "executive-dashboard.module.css");
const INSIGHTS = path.join(COMPONENTS, "dashboard-operational-insights.tsx");
const INSIGHT_STYLES = path.join(COMPONENTS, "dashboard-operational-insights.module.css");

const dashboardSource = () => fs.readFileSync(DASHBOARD, "utf8");
const dashboardStyles = () => fs.readFileSync(DASHBOARD_STYLES, "utf8");

test("Aven Dashboard composes official product components", () => {
  const source = dashboardSource();
  for (const component of [
    "PageHeader",
    "FilterBar",
    "ProviderSelector",
    "AccountSelector",
    "MetricCard",
    "ChartCard",
    "Section",
    "DataState",
    "CurrencyDisplay",
    "StatusIndicator",
    "ProviderBadge",
    "RecommendationCard",
    "ResourceIdentifier",
  ]) {
    assert.match(source, new RegExp(`<${component}\\b`), `${component} should be used by the Dashboard`);
  }
  assert.doesNotMatch(source, /@\/components\/page-header/);
  assert.doesNotMatch(source, /@\/components\/status-badge/);
  assert.doesNotMatch(source, /className="(?:panel|metric-card|dashboard-)/);
});

test("Dashboard preserves URL scope and existing query contracts", () => {
  const source = dashboardSource();
  assert.match(source, /parseDashboardSearchParams\(searchKey\)/);
  assert.match(source, /patchDashboardUrl\(searchKey, patch\)/);
  assert.match(source, /queryKeys\.dashboard\.summary\(state\.provider, state\.accountId\)/);
  assert.match(source, /path: `\/dashboard\/summary/);
  assert.match(source, /queryKeys\.collections\.options\(state\.provider, "", 100\)/);
  assert.match(source, /path: `\/collections\/options\?/);
  assert.match(source, /router\.replace\(`/);
});

test("Dashboard keeps currencies separate and uses CurrencyDisplay metadata", () => {
  const source = dashboardSource();
  assert.match(source, /totals\.map\(\(total\) =>/);
  assert.match(source, /<CurrencyDisplay[\s\S]*currency=\{total\.currency\}/);
  assert.match(source, /currencyDisplay="code"/);
  assert.match(source, /Moedas permanecem separadas; nenhum câmbio é inferido/);
  assert.doesNotMatch(source, /totals\.reduce\(/);
});

test("Dashboard analytical visualization uses real service distribution instead of fabricating cost history", () => {
  const source = dashboardSource();
  assert.match(source, /title="Concentração por serviço"/);
  assert.match(source, /summary\.by_service\.map/);
  assert.match(source, /Quantidade de oportunidades em aberto por serviço/);
  assert.doesNotMatch(source, /cost evolution|Evolução de custos/i);
});

test("Dashboard visual polish keeps cards content-driven and summary identifiers bounded", () => {
  const source = dashboardSource();
  const styles = dashboardStyles();
  assert.match(styles, /\.analysisGrid\s*\{[\s\S]*?align-items: start;/);
  assert.doesNotMatch(styles, /\.analysisGrid\s*\{[\s\S]*?align-items: stretch;/);
  assert.match(styles, /\.metricGrid > \*\s*\{[\s\S]*?align-content: start;/);
  assert.doesNotMatch(styles, /^\s*(?:height|min-height)\s*:/m);
  assert.match(source, /resource=\{[\s\S]*?<ResourceIdentifier/);
  assert.match(source, /technicalId=\{item\.resource_name \? undefined : item\.resource_id\}/);
  assert.doesNotMatch(source, /description=\{`[^`]*resource_id/);
  assert.ok(
    source.indexOf("<CollectionFailureOperationalInsights />") > source.indexOf("<DataState"),
    "operational activity should follow the primary executive summary",
  );
});

test("operational insights preserve isolated scoped query and refresh behavior", () => {
  const source = fs.readFileSync(INSIGHTS, "utf8");
  assert.match(source, /queryKeys\.dashboard\.operationalInsights\(state\.provider, state\.accountId\)/);
  assert.match(source, /path: `\/dashboard\/operational-insights/);
  assert.match(source, /const INSIGHT_REFRESH_INTERVAL = 45_000/);
  assert.match(source, /if \(request\.isLoading \|\| request\.error \|\| !failures\?\.count\) return null/);
  assert.match(source, /<Section/);
  assert.match(source, /<Alert/);
});

test("Dashboard standardizes loading, empty and error presentation", () => {
  const source = dashboardSource();
  assert.match(source, /<MetricCard[^>]*[\s\S]*loading/);
  assert.match(source, /<ChartCard[\s\S]*loading=\{summaryLoading\}/);
  assert.match(source, /<DataState[\s\S]*emptyTitle="Nenhum dado válido no escopo atual"/);
  assert.match(source, /errorFallback=/);
  assert.match(source, /Tentar novamente/);
});

test("Dashboard responsive composition degrades from four columns to one", () => {
  const styles = dashboardStyles();
  assert.match(styles, /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/);
  assert.match(styles, /@media \(max-width: 78rem\)[\s\S]*repeat\(2, minmax\(0, 1fr\)\)/);
  assert.match(styles, /@media \(max-width: 48rem\)[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
  assert.match(styles, /background: var\(--chart-series-1\)/);
});

test("hardcode gate is zero for all Dashboard files", () => {
  const violations = [
    ...scanDirectory(DASHBOARD),
    ...scanDirectory(DASHBOARD_STYLES),
    ...scanDirectory(INSIGHTS),
    ...scanDirectory(INSIGHT_STYLES),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
});

test("legacy Dashboard styles are removed from runtime and Aven documentation exists", () => {
  assert.equal(fs.existsSync(path.join(APP, "dashboard-executive.css")), false);
  assert.equal(fs.existsSync(path.join(APP, "dashboard-operational-insights.css")), false);
  const layout = fs.readFileSync(path.join(APP, "layout.tsx"), "utf8");
  assert.doesNotMatch(layout, /dashboard-executive\.css|dashboard-operational-insights\.css/);
  assert.ok(fs.existsSync(path.join(DOCS, "AVEN_DASHBOARD.md")));
  const readme = fs.readFileSync(path.join(DOCS, "README.md"), "utf8");
  assert.match(readme, /AVEN_DASHBOARD\.md/);
  assert.match(readme, /Page Composition Golden Reference/);
});
