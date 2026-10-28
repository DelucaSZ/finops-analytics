import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  buildCollectionQuery,
  parseCollectionQuery,
  patchCollectionQuery,
} from "../lib/collection-query.mjs";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Reports composes the official Aven asynchronous-history stack", async () => {
  const workspace = await source("../components/collection-workspace.tsx");
  for (const component of [
    "PageHeader",
    "Section",
    "FilterBar",
    "ProviderSelector",
    "AccountSelector",
    "StatusIndicator",
    "ProviderBadge",
    "Table",
    "Pagination",
    "Alert",
    "Skeleton",
    "EmptyState",
  ]) assert.ok(workspace.includes(component), `expected ${component} in Reports`);
  assert.ok(workspace.includes('title={collectionId ? `Relatório #${collectionId.slice(0, 8)}` : "Relatórios"}'));
  assert.ok(!workspace.includes("@/components/page-header"));
  assert.ok(!workspace.includes("StatusBadge"));
});

test("Reports preserves the real CollectionRun status model", async () => {
  const query = await source("../lib/collection-query.mjs");
  const workspace = await source("../components/collection-workspace.tsx");
  for (const status of ["RUNNING", "SUCCESS", "FAILED"]) {
    assert.ok(query.includes(status));
    assert.ok(workspace.includes(status));
  }
  for (const invented of ["queued", "expired", "cancelled"]) {
    assert.ok(!workspace.includes(`\"${invented}\"`));
  }
});

test("Reports polling remains conditional, visible-tab only and terminal-safe", async () => {
  const workspace = await source("../components/collection-workspace.tsx");
  assert.ok(workspace.includes('detail?.status === "RUNNING"'));
  assert.ok(workspace.includes('run.status === "RUNNING"'));
  assert.ok(workspace.includes("if (!hasRunning) return;"));
  assert.ok(workspace.includes('document.visibilityState !== "visible"'));
  assert.ok(workspace.includes("15000"));
  assert.ok(workspace.includes("window.clearInterval(timer)"));
});

test("Reports preserves server-side filters, sorting and pagination", () => {
  const state = parseCollectionQuery("provider=aws&account_id=123&status=SUCCESS&page=2&page_size=25&sort=opportunities_found&order=asc");
  assert.equal(state.provider, "aws");
  assert.equal(state.account_id, "123");
  assert.equal(state.status, "SUCCESS");
  assert.equal(state.page, 2);
  assert.equal(state.page_size, 25);
  assert.equal(state.sort, "opportunities_found");
  assert.equal(state.order, "asc");

  const query = new URLSearchParams(buildCollectionQuery(state));
  assert.equal(query.get("provider"), "aws");
  assert.equal(query.get("account_id"), "123");
  assert.equal(query.get("status"), "SUCCESS");
  assert.equal(query.get("page"), "2");
  assert.equal(query.get("page_size"), "25");

  const patched = new URLSearchParams(patchCollectionQuery(query.toString(), { status: "FAILED" }));
  assert.equal(patched.get("status"), "FAILED");
  assert.equal(patched.get("page"), "1");
});

test("Report generation UI preserves the existing async scan mutation without fabricating file completion", async () => {
  const launcher = await source("../components/manual-collection-launcher.tsx");
  for (const component of ["Dialog", "DialogTrigger", "DialogContent", "Select", "Button", "Alert", "useToast"]) {
    assert.ok(launcher.includes(component), `expected ${component} in generation flow`);
  }
  assert.ok(launcher.includes('`/cloud-accounts/${selected.id}/scans`'));
  assert.ok(launcher.includes('method: "POST"'));
  assert.ok(launcher.includes("if (submitting || !cloudAccountId) return;"));
  assert.ok(launcher.includes("Relatório enviado para processamento"));
  assert.ok(!launcher.includes("Relatório gerado com sucesso"));
  assert.ok(!launcher.includes("download"));
  assert.ok(!launcher.includes("signed"));
});

test("Aven AccountSelector supports remote option search for report account filters", async () => {
  const selectors = await source("../components/aven/selectors.tsx");
  assert.ok(selectors.includes("onSearchChange?: (value: string) => void"));
  assert.ok(selectors.includes("onSearchChange?.(value)"));
});

test("Reports is exposed in shared navigation without changing the existing route", async () => {
  const navigation = await source("../components/app-shell/navigation.ts");
  assert.ok(navigation.includes('{ href: "/collections", label: "Relatórios", icon: Activity }'));
  assert.ok(!navigation.includes('href: "/reports"'));
});

test("Reports loading, empty and failure states remain distinct", async () => {
  const workspace = await source("../components/collection-workspace.tsx");
  assert.ok(workspace.includes("Nenhum relatório corresponde aos filtros atuais"));
  assert.ok(workspace.includes("Nenhum relatório foi processado ainda"));
  assert.ok(workspace.includes("Falha durante o processamento"));
  assert.ok(workspace.includes("Não foi possível carregar os relatórios"));
  assert.ok(workspace.includes("Processamento em andamento"));
});

test("Reports does not take scroll ownership from Application Shell", async () => {
  const css = await source("../components/collection-workspace.module.css");
  assert.ok(!css.includes("height: 100vh"));
  assert.ok(!css.includes("height: 100dvh"));
  assert.doesNotMatch(css, /\.page\s*\{[^}]*overflow:\s*hidden;/s);
  assert.ok(!css.includes("overflow-x: auto"));
});

test("Reports files pass the Aven hardcode gate independently", async () => {
  const entries = [
    ["components/collection-workspace.tsx", await source("../components/collection-workspace.tsx")],
    ["components/collection-workspace.module.css", await source("../components/collection-workspace.module.css")],
    ["components/manual-collection-launcher.tsx", await source("../components/manual-collection-launcher.tsx")],
    ["components/manual-collection-launcher.module.css", await source("../components/manual-collection-launcher.module.css")],
    ["app/collections/page.tsx", await source("../app/collections/page.tsx")],
    ["app/collections/[collectionId]/page.tsx", await source("../app/collections/[collectionId]/page.tsx")],
  ];
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});

test("Reports is included in normal lint and design-system scopes", async () => {
  const packageJson = await source("../package.json");
  const gate = await source("../scripts/check-design-system.mjs");
  assert.ok(packageJson.includes("--dir app/collections"));
  assert.ok(packageJson.includes("--file components/collection-workspace.tsx"));
  assert.ok(packageJson.includes("--file components/manual-collection-launcher.tsx"));
  assert.ok(gate.includes('path.join(ROOT, "components", "collection-workspace.tsx")'));
  assert.ok(gate.includes('path.join(ROOT, "components", "manual-collection-launcher.tsx")'));
  assert.ok(gate.includes('path.join(ROOT, "app", "collections", "page.tsx")'));
});

test("Reports documentation records real architecture and unavailable file-export features", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_REPORTS.md", import.meta.url), "utf8");
  for (const phrase of [
    "Existing Report Architecture",
    "CollectionRun",
    "Status Model",
    "Polling / Refresh",
    "Download",
    "Generated file formats: N/A",
    "RUNNING",
    "SUCCESS",
    "FAILED",
    "Task 24.16 Readiness",
  ]) assert.ok(docs.includes(phrase), `missing Reports documentation contract: ${phrase}`);
});
