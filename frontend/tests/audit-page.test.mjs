import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/settings/audit/page.tsx", import.meta.url);

test("Audit page renders unified security and administrative events", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('event_kind: "security" | "administrative"'));
  assert.ok(page.includes('<option value="administrative">Administrativos</option>'));
  assert.ok(page.includes('<option value="security">Segurança</option>'));
  assert.ok(page.includes('if (item.source === "SYSTEM")'));
  assert.ok(page.includes('item.action === "auth.login_failed"'));
});

test("Audit page supports actor and affected-user autocomplete", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("function UserAutocomplete"));
  assert.ok(page.includes('label="Executado por"'));
  assert.ok(page.includes('label="Usuário afetado"'));
  assert.ok(page.includes("/audit/users?q="));
  assert.ok(page.includes("window.setTimeout"));
  assert.ok(page.includes('params.set("actor_id", actorId)'));
  assert.ok(page.includes('params.set("actor_search", actorQuery.trim())'));
  assert.ok(page.includes('params.set("subject_user_id", subjectId)'));
  assert.ok(page.includes('params.set("subject_user_search", subjectQuery.trim())'));
});

test("Audit page exposes operational filters and persists them in URL", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('event_kind: eventKind'));
  assert.ok(page.includes('params.set("module", module)'));
  assert.ok(page.includes('params.set("action", action)'));
  assert.ok(page.includes('params.set("source", source)'));
  assert.ok(page.includes('params.set("from", fromIso)'));
  assert.ok(page.includes('params.set("to", toIso)'));
  assert.ok(page.includes("window.history.replaceState"));
  assert.ok(page.includes("Últimas 24h"));
  assert.ok(page.includes("7 dias"));
  assert.ok(page.includes("30 dias"));
  assert.ok(page.includes("Hoje"));
  assert.ok(page.includes("Limpar filtros"));
});

test("Audit page summarizes changes and opens a reusable detail view", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes(".slice(0, 2)"));
  assert.ok(page.includes("Alterações resumidas por limite de tamanho"));
  assert.ok(page.includes("Ver detalhes"));
  assert.ok(page.includes('aria-label="Detalhes do evento de auditoria"'));
  assert.ok(page.includes("Correlation ID"));
  assert.ok(page.includes("Contexto seguro"));
  assert.ok(page.includes("Antes"));
  assert.ok(page.includes("Depois"));
  assert.ok(!page.includes("JSON.stringify(item.changes"));
  assert.ok(!page.includes("<pre>{"));
});

test("Audit page keeps server-side pagination and result count", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("const PAGE_SIZE = 50"));
  assert.ok(page.includes("offset + PAGE_SIZE >= data.total"));
  assert.ok(page.includes("setOffset(Math.max(0, offset - PAGE_SIZE))"));
  assert.ok(page.includes("eventos encontrados"));
  assert.ok(page.includes("Nenhum evento encontrado para os filtros atuais"));
  assert.ok(page.includes("Carregando histórico"));
});
