import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const read = (relative) =>
  readFile(new URL(relative, import.meta.url), "utf8");

test("shared status presentation normalizes backend enums and keeps lifecycle labels friendly", async () => {
  const badge = await read("../components/status-badge.tsx");
  const css = await read("../app/globals.css");

  assert.match(badge, /toLowerCase\(\)/);
  assert.match(badge, /success: "Concluída"/);
  assert.match(badge, /treated: "Tratada"/);
  assert.match(badge, /rejected: "Rejeitada"/);
  assert.match(css, /status-success/);
});

test("auth boundaries use the app router event instead of hard reloads", async () => {
  const api = await read("../lib/api.ts");
  const shell = await read("../components/app-shell.tsx");

  assert.doesNotMatch(api, /window\.location\.(assign|replace)|location\.reload/);
  assert.match(api, /deepops:auth-redirect/);
  assert.match(shell, /deepops:auth-redirect/);
  assert.match(shell, /router\.replace\(path\)/);
});

test("decision overlays trap focus, preserve form input on backdrop clicks and expose field errors", async () => {
  const hook = await read("../lib/use-dialog-focus.ts");
  const dialog = await read("../components/opportunity-decision-dialog.tsx");

  assert.match(hook, /event\.key !== "Tab"/);
  assert.match(hook, /previousFocus\.focus\(\)/);
  assert.match(dialog, /useDialogFocus/);
  assert.doesNotMatch(dialog, /dialog-backdrop" role="presentation" onMouseDown/);
  assert.match(dialog, /aria-invalid/);
  assert.match(dialog, /decision-reason-error/);
  assert.match(dialog, /button danger/);
});

test("operational filters show applied context and only offer clear when meaningful", async () => {
  const opportunities = await read("../app/opportunities/page.tsx");
  const collections = await read("../components/collection-workspace.tsx");

  assert.match(opportunities, /Filtros ativos/);
  assert.match(opportunities, /filter-chip/);
  assert.match(collections, /Filtros ativos/);
  assert.match(collections, /hasFilters &&/);
});

test("comparison drill-down preserves return context and lifecycle mutations invalidate comparison cache", async () => {
  const comparison = await read("../app/collections/[collectionId]/compare/page.tsx");
  const opportunities = await read("../app/opportunities/page.tsx");

  assert.match(comparison, /return_to=/);
  assert.match(comparison, /comparisonReturnTo/);
  assert.match(opportunities, /returnTo\.startsWith\("\/collections\/"\)/);
  assert.match(opportunities, /invalidateApiQueries\(\["collections", "comparison"\]\)/);
  assert.doesNotMatch(comparison, />ANTERIOR</);
  assert.doesNotMatch(comparison, />ATUAL</);
});

test("user-facing collection copy avoids raw CollectionRun and SUCCESS labels in primary screens", async () => {
  const home = await read("../app/page.tsx");
  const collections = await read("../components/collection-workspace.tsx");
  const comparison = await read("../app/collections/[collectionId]/compare/page.tsx");

  assert.doesNotMatch(home, /coletas SUCCESS|Sem SUCCESS|SUCCESS com avisos/);
  assert.doesNotMatch(collections, /<h2>CollectionRun<\/h2>/);
  assert.doesNotMatch(comparison, /Comparando CollectionRuns|>ANTERIOR<|>ATUAL</);
});
