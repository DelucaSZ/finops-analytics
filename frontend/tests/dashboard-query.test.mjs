import test from "node:test";
import assert from "node:assert/strict";
import {
  buildDashboardApiQuery,
  parseDashboardSearchParams,
  patchDashboardUrl,
  scopedDashboardHref,
} from "../lib/dashboard-query.mjs";

test("dashboard scope round-trips provider and native account id", () => {
  const state = parseDashboardSearchParams(
    "provider=AWS&account_id=111111111111",
  );
  assert.deepEqual(state, {
    provider: "aws",
    accountId: "111111111111",
  });
  assert.equal(
    buildDashboardApiQuery(state),
    "provider=aws&account_id=111111111111",
  );
});

test("changing cloud can clear account while preserving shareable scope", () => {
  const params = patchDashboardUrl(
    "provider=aws&account_id=111111111111",
    { provider: "oci", account_id: null },
  );
  assert.equal(params.get("provider"), "oci");
  assert.equal(params.has("account_id"), false);
});

test("drill-down preserves scope and adds operational filters", () => {
  const href = scopedDashboardHref(
    "/opportunities",
    { provider: "aws", accountId: "111111111111" },
    { current: "true", status: "open", severity: "high" },
  );
  const url = new URL(href, "http://deepops.local");
  assert.equal(url.pathname, "/opportunities");
  assert.equal(url.searchParams.get("provider"), "aws");
  assert.equal(url.searchParams.get("account_id"), "111111111111");
  assert.equal(url.searchParams.get("current"), "true");
  assert.equal(url.searchParams.get("status"), "open");
  assert.equal(url.searchParams.get("severity"), "high");
});

test("home uses the executive summary and does not depend on collection health", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );
  const dashboard = await readFile(
    new URL("../components/executive-dashboard.tsx", import.meta.url),
    "utf8",
  );
  const source = `${page}\n${dashboard}`;

  assert.match(source, /\/dashboard\/summary/);
  assert.match(source, /\/collections\/options/);
  assert.match(source, /current: "true"/);
  assert.match(source, /DashboardOperationalInsights/);
  assert.doesNotMatch(source, /\/dashboard\/collection-health/);
  assert.doesNotMatch(source, /Última execução x última coleta válida/);
  assert.doesNotMatch(source, /Sem SUCCESS/);
  assert.doesNotMatch(source, /api<AwsAccount\[]>/);
  assert.doesNotMatch(source, /Cobertura inicial/);
  assert.doesNotMatch(source, />9\/9</);
});
