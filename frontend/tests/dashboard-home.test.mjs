import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const pageSource = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");
const dashboardSource = readFileSync(
  new URL("../components/executive-dashboard.tsx", import.meta.url),
  "utf8",
);

const homeSource = `${pageSource}\n${dashboardSource}`;

test("dashboard home does not fetch or render detailed collection health", () => {
  assert.doesNotMatch(homeSource, /\/dashboard\/collection-health/);
  assert.doesNotMatch(homeSource, /Falhas na última execução/);
  assert.doesNotMatch(homeSource, /Saúde das coletas/);
  assert.match(homeSource, /DashboardOperationalInsights/);
});

test("dashboard home exposes Aven executive dimensions and multi-currency savings", () => {
  assert.match(homeSource, /<PageHeader/);
  assert.match(homeSource, /<FilterBar/);
  assert.match(homeSource, /t\("metrics\.openOpportunities"\)/);
  assert.match(homeSource, /t\("metrics\.monthlySavings"\)/);
  assert.match(homeSource, /t\("metrics\.newSincePrevious"\)/);
  assert.match(homeSource, /t\("metrics\.validScopes"\)/);
  assert.match(homeSource, /t\("charts\.serviceConcentration"\)/);
  assert.match(homeSource, /t\("sections\.lifecycle"\)/);
  assert.match(homeSource, /t\("sections\.cloudDistribution"\)/);
  assert.match(homeSource, /t\("sections\.topOpportunities"\)/);
  assert.match(homeSource, /SavingsValues/);
  assert.match(homeSource, /CurrencyDisplay/);
  assert.doesNotMatch(homeSource, /Evolução de custos/);
});
