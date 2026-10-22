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

test("dashboard home exposes executive dimensions and multi-currency savings", () => {
  assert.match(homeSource, /Oportunidades em aberto/);
  assert.match(homeSource, /Economia potencial/);
  assert.match(homeSource, /Oportunidades por severidade/);
  assert.match(homeSource, /Distribuição por provider/);
  assert.match(homeSource, /Contas com maior backlog/);
  assert.match(homeSource, /Top serviços e regras/);
  assert.match(homeSource, /Maiores oportunidades/);
  assert.match(homeSource, /SavingsValues/);
});
