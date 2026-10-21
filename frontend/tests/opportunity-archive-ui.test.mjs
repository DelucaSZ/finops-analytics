import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const opportunityPage = readFileSync(new URL("../app/opportunities/page.tsx", import.meta.url), "utf8");
const detail = readFileSync(new URL("../components/opportunity-detail.tsx", import.meta.url), "utf8");
const archiveDialog = readFileSync(new URL("../components/opportunity-archive-dialog.tsx", import.meta.url), "utf8");
const cycles = readFileSync(new URL("../app/opportunities/history-cycles/page.tsx", import.meta.url), "utf8");

test("operational page exposes individual, selected and server-side filtered archive flows", () => {
  assert.match(opportunityPage, /Arquivar selecionadas/);
  assert.match(opportunityPage, /Arquivar todas deste filtro/);
  assert.match(opportunityPage, /Arquivar todo o backlog/);
  assert.match(opportunityPage, /\/opportunities\/bulk\/archive/);
  assert.match(opportunityPage, /\/opportunities\/\$\{id\}\/archive/);
  assert.match(opportunityPage, /OpportunityArchiveDialog/);
});

test("archive confirmation previews the server-side scope and uses explicit counts", () => {
  assert.match(archiveDialog, /\/opportunities\/archive-preview/);
  assert.match(archiveDialog, /\/opportunities\/archive-by-filter/);
  assert.match(archiveDialog, /Arquivar \$\{number\(preview\.to_archive\)\} oportunidades/);
  assert.match(archiveDialog, /todas as oportunidades operacionais atualmente ativas/);
});

test("detail drawer offers archive while archived findings keep restore behavior", () => {
  assert.match(detail, /onArchive: \(id: string\) => void/);
  assert.match(detail, /<Archive size=\{17\} \/> Arquivar/);
  assert.match(detail, /Reabrir oportunidade/);
  assert.match(detail, /Desarquivar/);
});

test("cycle screen previews combined close and blocks running collections", () => {
  assert.match(cycles, /\/opportunities\/period-close\/preview/);
  assert.match(cycles, /\/opportunities\/period-close/);
  assert.match(cycles, /Snapshots a gerar/);
  assert.match(cycles, /Itens operacionais a arquivar/);
  assert.match(cycles, /failed_collection_runs/);
  assert.match(cycles, /running_collection_runs > 0/);
  assert.match(cycles, /Fechar período e arquivar/);
});
