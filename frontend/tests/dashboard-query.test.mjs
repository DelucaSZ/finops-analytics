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

test("home uses aggregated dashboard APIs and no longer rebuilds metrics from accounts", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(
    new URL("../app/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(page, /\/dashboard\/summary/);
  assert.match(page, /\/dashboard\/collection-health/);
  assert.match(page, /\/collections\/options/);
  assert.match(page, /current: "true"/);
  assert.match(page, /Última execução x última coleta válida/);
  assert.match(page, /Sem SUCCESS/);
  assert.doesNotMatch(page, /api<AwsAccount\[]>/);
  assert.doesNotMatch(page, /Cobertura inicial/);
  assert.doesNotMatch(page, />9\/9</);
});
