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

test("defaults to the OPEN operational workspace with server-side pagination defaults", () => {
  const state = parseOpportunitySearchParams("");
  assert.equal(state.view, "operational");
  assert.equal(state.status, "open");
  assert.equal(state.page, 1);
  assert.equal(state.pageSize, 50);
  assert.equal(state.sort, "last_seen_at");
  assert.equal(state.order, "desc");
});

test("history view defaults to archived records ordered by archived_at desc", () => {
  const state = parseOpportunitySearchParams("view=history");
  assert.equal(state.view, "history");
  assert.equal(state.status, "");
  assert.equal(state.sort, "archived_at");
  assert.equal(state.order, "desc");
  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(query.get("archive_state"), "archived");
  assert.equal(query.get("sort"), "archived_at");
  assert.equal(query.has("status"), false);
  assert.equal(query.has("current"), false);
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

test("builds the operational list query contract", () => {
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
  assert.equal(query.has("archive_state"), false);
});

test("builds history filters entirely on the backend query", () => {
  const state = parseOpportunitySearchParams([
    "view=history",
    "status=treated",
    "provider=oci",
    "account_id=ocid1.tenancy.oc1..example",
    "service=BlockStorage",
    "presence_status=resolved_externally",
    "archived_from=2026-08-01",
    "archived_to=2026-10-13",
    "archive_reason=RETENTION_POLICY",
  ].join("&"));
  const query = new URLSearchParams(buildOpportunityApiQuery(state));
  assert.equal(query.get("archive_state"), "archived");
  assert.equal(query.get("status"), "treated");
  assert.equal(query.get("provider"), "oci");
  assert.equal(query.get("account_id"), "ocid1.tenancy.oc1..example");
  assert.equal(query.get("service"), "BlockStorage");
  assert.equal(query.get("presence_status"), "resolved_externally");
  assert.equal(query.get("archived_from"), "2026-08-01T00:00:00Z");
  assert.equal(query.get("archived_to"), "2026-10-13T23:59:59.999999Z");
  assert.equal(query.get("archive_reason"), "RETENTION_POLICY");
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

test("history stats retain historical dimensions but do not mix status into grouping", () => {
  const state = parseOpportunitySearchParams("view=history&status=rejected&presence_status=missing&archive_reason=MANUAL");
  const query = new URLSearchParams(buildOpportunityStatsQuery(state));
  assert.equal(query.get("archive_state"), "archived");
  assert.equal(query.get("presence_status"), "missing");
  assert.equal(query.get("archive_reason"), "MANUAL");
  assert.equal(query.has("status"), false);
});

test("current-state context survives operational API queries only", () => {
  const state = parseOpportunitySearchParams(
    "provider=aws&account_id=123&status=open&current=true",
  );
  assert.equal(state.current, true);
  const list = new URLSearchParams(buildOpportunityApiQuery(state));
  const stats = new URLSearchParams(buildOpportunityStatsQuery(state));
  assert.equal(list.get("current"), "true");
  assert.equal(stats.get("current"), "true");
  assert.equal(list.get("provider"), "aws");
  assert.equal(list.get("account_id"), "123");

  const history = parseOpportunitySearchParams("view=history&current=true");
  assert.equal(history.current, false);
  assert.equal(new URLSearchParams(buildOpportunityApiQuery(history)).has("current"), false);
});

test("changing a filter resets page while explicit pagination does not", () => {
  const filtered = patchOpportunityUrl("status=open&page=4&severity=low", { severity: "high" });
  assert.equal(filtered.get("page"), "1");
  assert.equal(filtered.get("severity"), "high");

  const paged = patchOpportunityUrl(filtered, { page: 3 }, { resetPage: false });
  assert.equal(paged.get("page"), "3");
});

test("changing lifecycle status preserves operational filters, page size and sorting", () => {
  const current = [
    "status=open",
    "provider=oci",
    "account_id=ocid1.tenancy.oc1..example",
    "region=sa-saopaulo-1",
    "service=compute",
    "resource_type=instance",
    "severity=high",
    "rule=idle_instance",
    "collection_run_id=run-22",
    "resource_id=instance-1",
    "search=idle",
    "page=4",
    "page_size=100",
    "sort=severity",
    "order=asc",
    "current=true",
  ].join("&");

  const next = patchOpportunityUrl(current, { status: "treated" });

  assert.equal(next.get("status"), "treated");
  assert.equal(next.get("provider"), "oci");
  assert.equal(next.get("account_id"), "ocid1.tenancy.oc1..example");
  assert.equal(next.get("region"), "sa-saopaulo-1");
  assert.equal(next.get("service"), "compute");
  assert.equal(next.get("resource_type"), "instance");
  assert.equal(next.get("severity"), "high");
  assert.equal(next.get("rule"), "idle_instance");
  assert.equal(next.get("collection_run_id"), "run-22");
  assert.equal(next.get("resource_id"), "instance-1");
  assert.equal(next.get("search"), "idle");
  assert.equal(next.get("current"), "true");
  assert.equal(next.get("page"), "1");
  assert.equal(next.get("page_size"), "100");
  assert.equal(next.get("sort"), "severity");
  assert.equal(next.get("order"), "asc");
});

test("history URLs preserve broad filters and can clear the optional human status", () => {
  const current = "view=history&provider=aws&status=treated&presence_status=missing&page=4&archived_from=2026-01-01";
  const next = patchOpportunityUrl(current, { status: null, archive_reason: "RETENTION_POLICY" });
  assert.equal(next.get("view"), "history");
  assert.equal(next.get("provider"), "aws");
  assert.equal(next.has("status"), false);
  assert.equal(next.get("presence_status"), "missing");
  assert.equal(next.get("archived_from"), "2026-01-01");
  assert.equal(next.get("archive_reason"), "RETENTION_POLICY");
  assert.equal(next.get("page"), "1");
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

test("preserves the three lifecycle states used by the operational workspace tabs", () => {
  for (const status of ["open", "treated", "rejected"]) {
    const state = parseOpportunitySearchParams(`status=${status}`);
    assert.equal(state.status, status);
    assert.equal(new URLSearchParams(buildOpportunityApiQuery(state)).get("status"), status);
  }
});

test("workspace source exposes history without regressing operational semantics", async () => {
  const { readFile } = await import("node:fs/promises");
  const page = await readFile(new URL("../app/opportunities/page.tsx", import.meta.url), "utf8");
  const detail = await readFile(new URL("../components/opportunity-detail.tsx", import.meta.url), "utf8");
  const archiveHistory = await readFile(new URL("../components/opportunity-archive-history.tsx", import.meta.url), "utf8");
  const dialog = await readFile(new URL("../components/opportunity-decision-dialog.tsx", import.meta.url), "utf8");

  for (const label of ["Abertas", "Tratadas", "Rejeitadas", "Histórico"]) {
    assert.match(page, new RegExp(label));
  }
  for (const primitive of ["FilterBar", "Tabs", "TabsList", "TabsTrigger", "Section", "MetricCard"]) {
    assert.match(page, new RegExp(`\\b${primitive}\\b`), `expected Aven component ${primitive}`);
  }

  assert.match(page, /archive_state/);
  assert.match(page, /Presença técnica/);
  assert.match(page, /Arquivada desde/);
  assert.match(page, /Desarquivar/);
  assert.match(page, /Moedas preservadas separadamente; nenhuma conversão FX é aplicada/);
  assert.match(page, /totals\[currency\] = \(totals\[currency\] \|\| 0\) \+ amount/);
  assert.doesNotMatch(page, /exchangeRate|fxRate|convertCurrency/);
  assert.match(page, /\/opportunities\/stats/);
  assert.match(page, /opportunity_id/);
  assert.match(page, /Selecionar página atual/);
  assert.match(page, /buildLifecycleRequest/);
  assert.match(page, /archiveSucceeded/);
  assert.match(page, /restoreHistoryRow/);
  assert.doesNotMatch(page, /window\.prompt/);
  assert.doesNotMatch(page, /location\.reload|window\.location\.reload/);

  assert.match(detail, /Por que|FindingEvidence/);
  assert.match(detail, /Histórico de detecção/);
  assert.match(detail, /Histórico de decisões/);
  assert.match(detail, /OpportunityPresenceHistory/);
  assert.match(detail, /OpportunityArchiveHistory/);
  assert.match(detail, /StatusIndicator status=\{statusTone\(detail\.status\)\} label=\{statusLabel\(detail\.status\)\}/);
  assert.match(detail, /StatusIndicator status=\{statusTone\(detail\.presence_status\)\} label=\{statusLabel\(detail\.presence_status\)\}/);
  assert.match(detail, /Decisão atual/);
  assert.match(detail, /Arquivada em/);
  assert.match(detail, /Desarquivar/);
  assert.match(detail, /Ver histórico completo/);
  assert.match(archiveHistory, /Política de retenção/);
  assert.match(archiveHistory, /Reaparecimento automático/);
  assert.match(dialog, /FALSE_POSITIVE/);
  assert.match(dialog, /OPERATIONAL_EXCEPTION/);
  assert.match(dialog, /OTHER/);
});
