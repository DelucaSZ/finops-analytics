import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  buildLifecycleRequest,
  buildOpportunityApiQuery,
  parseOpportunitySearchParams,
} from "../lib/opportunity-query.mjs";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Recommendations composes the official Aven decision-support stack", async () => {
  const page = await source("../app/opportunities/page.tsx");
  for (const component of [
    "PageHeader",
    "Section",
    "MetricCard",
    "FilterBar",
    "AccountSelector",
    "ProviderSelector",
    "RecommendationCard",
    "ProviderBadge",
    "ResourceIdentifier",
    "CurrencyDisplay",
    "StatusIndicator",
    "DataState",
    "Table",
    "Pagination",
    "Checkbox",
    "Alert",
    "Skeleton",
  ]) assert.ok(page.includes(component), `expected ${component} in Recommendations`);

  assert.ok(!page.includes('from "@/components/page-header"'));
  assert.ok(!page.includes('from "@/components/status-badge"'));
  assert.ok(!page.includes("function RecommendationCard"));
});

test("Recommendations preserves the server-side query boundary", async () => {
  const page = await source("../app/opportunities/page.tsx");
  assert.ok(page.includes("buildOpportunityApiQuery"));
  assert.ok(page.includes("buildOpportunityStatsQuery"));
  assert.ok(page.includes('path: `/opportunities?${listQuery}`'));
  assert.ok(page.includes('path: `/opportunities/stats${statsQuery ? `?${statsQuery}` : ""}`'));
  assert.ok(page.includes("350"), "search debounce must remain in place");
  assert.ok(page.includes("keepPreviousData: true"));
  assert.ok(page.includes("prefetchApiQuery<OpportunityPage>"));
  assert.ok(!page.includes("filter((finding) => finding.title"), "search must not filter a partial page client-side");
});

test("Recommendations URL state preserves status, filters, sorting and pagination", () => {
  const state = parseOpportunitySearchParams(new URLSearchParams("provider=aws&account_id=123&region=us-east-1&service=EC2&resource_type=instance&severity=high&rule=idle_instance&search=api&page=2&page_size=25&sort=estimated_savings&order=desc"));
  assert.equal(state.status, "open");
  assert.equal(state.provider, "aws");
  assert.equal(state.accountId, "123");
  assert.equal(state.region, "us-east-1");
  assert.equal(state.service, "EC2");
  assert.equal(state.resourceType, "instance");
  assert.equal(state.severity, "high");
  assert.equal(state.rule, "idle_instance");
  assert.equal(state.search, "api");
  assert.equal(state.page, 2);
  assert.equal(state.pageSize, 25);
  assert.equal(state.sort, "estimated_savings");

  const query = new URLSearchParams(buildOpportunityApiQuery(state, { now: new Date("2026-10-27T12:00:00Z") }));
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("account_id"), "123");
  assert.equal(query.get("severity"), "high");
  assert.equal(query.get("search"), "api");
  assert.equal(query.get("page"), "2");
});

test("Recommendations preserves real lifecycle actions without an apply-optimization path", async () => {
  const page = await source("../app/opportunities/page.tsx");
  for (const action of ["treat", "reject", "reopen"]) {
    const request = buildLifecycleRequest({ action, opportunityIds: ["opp-1"], bulk: false });
    assert.equal(request.path, `/opportunities/opp-1/${action}`);
  }
  assert.ok(page.includes("OpportunityDecisionDialog"));
  assert.ok(page.includes("OpportunityArchiveDialog"));
  assert.ok(page.includes("restoreHistoryRow"));
  assert.ok(!/apply optimization/i.test(page));
  assert.ok(!/apply-optimization/i.test(page));
});

test("Recommendations preserves savings currency and monthly semantics", async () => {
  const page = await source("../app/opportunities/page.tsx");
  assert.ok(page.includes("finding.estimated_monthly_savings"));
  assert.ok(page.includes("finding.currency"));
  assert.ok(page.includes("<CurrencyDisplay"));
  assert.ok(page.includes("/mês"));
  assert.ok(page.includes('finding.rule_key === "cost_growth_anomaly"'));
  assert.ok(page.includes("Não estimada"));
  assert.ok(page.includes("pageSavingsEntries"));
  assert.ok(!page.includes('finding.currency || "USD"'));
  assert.ok(!page.includes("exchangeRate"));
  assert.ok(!page.includes("convertCurrency"));
});

test("Recommendations keeps confidence distinct and backend-owned", async () => {
  const page = await source("../app/opportunities/page.tsx");
  assert.ok(page.includes("finding.confidence"));
  assert.ok(page.includes("confidenceTone(finding.confidence)"));
  assert.ok(!page.includes("PercentageDisplay"), "categorical/string confidence must not be converted into a fake percentage");
  assert.ok(!page.includes("confidenceScore"));
});

test("Recommendations switches between curated cards and dense tables by real volume", async () => {
  const page = await source("../app/opportunities/page.tsx");
  assert.ok(page.includes("total <= 6"));
  assert.ok(page.includes("<RecommendationCard"));
  assert.ok(page.includes("<Table aria-label="));
  assert.ok(page.includes("ResourceIdentifier"));
  assert.ok(page.includes("ProviderBadge"));
});

test("Recommendations differentiates filtered empty state and avoids false optimization claims", async () => {
  const page = await source("../app/opportunities/page.tsx");
  assert.ok(page.includes("Nenhuma oportunidade corresponde aos filtros"));
  assert.ok(page.includes("A engine não retornou recomendações nesse estado"));
  assert.ok(!/100% otimizado/i.test(page));
});

test("Recommendations page does not take scroll ownership from Application Shell", async () => {
  const css = await source("../app/opportunities/opportunities.module.css");
  assert.ok(!css.includes("height: 100vh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.ok(!css.includes("overflow-x: auto"), "horizontal table containment belongs to the Table primitive");
});

test("Recommendations files pass the Aven hardcode gate independently", async () => {
  const entries = [
    ["app/opportunities/page.tsx", await source("../app/opportunities/page.tsx")],
    ["app/opportunities/opportunities.module.css", await source("../app/opportunities/opportunities.module.css")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});

test("Recommendations is included in normal lint and design-system scopes", async () => {
  const packageJson = await source("../package.json");
  const gate = await source("../scripts/check-design-system.mjs");
  assert.ok(packageJson.includes("--dir app/opportunities"));
  assert.ok(gate.includes('path.join(ROOT, "app", "opportunities")'));
});

test("Recommendations documentation records the decision-support contracts", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_RECOMMENDATIONS.md", import.meta.url), "utf8");
  for (const phrase of [
    "Recommendation Model",
    "Potential Savings",
    "Confidence",
    "server-side filters/search/sort/pagination",
    "different currencies are never silently summed together",
    "Theme state is absent from opportunity query keys",
    "Golden Reference Alignment",
  ]) assert.ok(docs.includes(phrase), `missing documentation contract: ${phrase}`);
});
