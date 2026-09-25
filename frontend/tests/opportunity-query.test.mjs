import test from "node:test";
import assert from "node:assert/strict";
import {
  buildLifecycleRequest,
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
  rejectionRequiresNote,
} from "../lib/opportunity-query.mjs";

test("defaults to the OPEN workspace with server-side pagination defaults", () => {
  const state = parseOpportunitySearchParams("");
  assert.equal(state.status, "open");
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 50);
  assert.equal(state.sort, "last_seen_at");
  assert.equal(state.order, "desc");
});

test("restores supported filters, status, pagination and sorting from URL", () => {
  const state = parseOpportunitySearchParams("status=treated&provider=aws&account_id=123&region=us-east-1&severity=high&rule=ebs_unattached&collection_run_id=run-1&search=volume&page=3&page_size=100&sort=severity&order=asc");
  assert.deepEqual(
    {
      status: state.status,
      provider: state.provider,
      accountId: state.accountId,
      region: state.region,
      severity: state.severity,
      rule: state.rule,
      collectionRunId: state.collectionRunId,
      search: state.search,
      page: state.page,
      pageSize: state.pageSize,
      sort: state.sort,
      order: state.order,
    },
    {
      status: "treated",
      provider: "aws",
      accountId: "123",
      region: "us-east-1",
      severity: "high",
      rule: "ebs_unattached",
      collectionRunId: "run-1",
      search: "volume",
      page: 3,
      pageSize: 100,
      sort: "severity",
      order: "asc",
    },
  );
});

test("builds the exact Stage 4 list query contract", () => {
  const state = parseOpportunitySearchParams("status=rejected&provider=aws&account_id=123&severity=medium&rule_key=missing_required_tags&page=2&sort=estimated_savings&order=desc");
  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(query.get("status"), "rejected");
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("account_id"), "123");
  assert.equal(query.get("severity"), "medium");
  assert.equal(query.get("rule"), "missing_required_tags");
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("sort"), "estimated_savings");
  assert.equal(query.has("rule_key"), false);
});

test("stats query keeps global filters but omits status and pagination", () => {
  const state = parseOpportunitySearchParams("status=treated&provider=aws&account_id=123&severity=high&page=7&search=abc");
  const query = new URLSearchParams(buildOpportunityStatsQuery(state));
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("account_id"), "123");
  assert.equal(query.get("severity"), "high");
  assert.equal(query.get("search"), "abc");
  assert.equal(query.has("status"), false);
  assert.equal(query.has("page"), false);
});

test("changing a filter resets page while explicit pagination does not", () => {
  const filtered = patchOpportunityUrl("status=open&page=4&severity=low", { severity: "high" });
  assert.equal(filtered.get("page"), "1");
  assert.equal(filtered.get("severity"), "high");

  const paged = patchOpportunityUrl(filtered, { page: 3 }, { resetPage: false });
  assert.equal(paged.get("page"), "3");
});

test("builds individual and bulk lifecycle requests without optimistic semantics", () => {
  assert.deepEqual(
    buildLifecycleRequest({ action: "treat", opportunityIds: ["opp-1"], note: "feito", bulk: false }),
    { path: "/opportunities/opp-1/treat", body: { note: "feito" } },
  );
  assert.deepEqual(
    buildLifecycleRequest({ action: "reject", opportunityIds: ["opp-1", "opp-2"], reason: "RISK_ACCEPTED", note: "aprovado", bulk: true }),
    { path: "/opportunities/bulk/reject", body: { reason: "RISK_ACCEPTED", note: "aprovado", opportunity_ids: ["opp-1", "opp-2"] } },
  );
  assert.deepEqual(
    buildLifecycleRequest({ action: "reopen", opportunityIds: ["opp-1"], bulk: false }),
    { path: "/opportunities/opp-1/reopen", body: {} },
  );
});

test("OTHER is the only rejection reason that requires a note in the client", () => {
  assert.equal(rejectionRequiresNote("OTHER"), true);
  assert.equal(rejectionRequiresNote("FALSE_POSITIVE"), false);
});

test("preserves the three lifecycle states used by the workspace tabs", () => {
  for (const status of ["open", "treated", "rejected"]) {
    const state = parseOpportunitySearchParams(`status=${status}`);
    assert.equal(state.status, status);
    assert.equal(new URLSearchParams(buildOpportunityApiQuery(state)).get("status"), status);
  }
});

test("workspace source keeps Stage 5 operational semantics without legacy prompts or reloads", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(new URL("../app/opportunities/page.tsx", import.meta.url), "utf8");
  const detail = await readFile(new URL("../components/opportunity-detail.tsx", import.meta.url), "utf8");
  const dialog = await readFile(new URL("../components/opportunity-decision-dialog.tsx", import.meta.url), "utf8");

  assert.match(page, /Abertas/);
  assert.match(page, /Tratadas/);
  assert.match(page, /Rejeitadas/);
  assert.match(page, /\/opportunities\/stats/);
  assert.match(page, /opportunity_id/);
  assert.match(page, /Selecionar página atual/);
  assert.doesNotMatch(page, /window\.prompt/);
  assert.doesNotMatch(page, /location\.reload|window\.location\.reload/);

  assert.match(detail, /Por que|FindingEvidence/);
  assert.match(detail, /Histórico de detecção/);
  assert.match(detail, /Histórico de decisões/);
  assert.match(detail, /Ver histórico completo/);
  assert.match(dialog, /FALSE_POSITIVE/);
  assert.match(dialog, /OPERATIONAL_EXCEPTION/);
  assert.match(dialog, /OTHER/);
});
