import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/settings/audit/page.tsx", import.meta.url);

test("Audit page keeps unified security and administrative events", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('event_kind: "security" | "administrative"'));
  assert.ok(page.includes('<option value="administrative">Administrativos</option>'));
  assert.ok(page.includes('<option value="security">Segurança</option>'));
  assert.ok(page.includes('item.event_kind === "administrative" && item.source === "SYSTEM"'));
  assert.ok(page.includes('item.action === "auth.login_failed"'));
});

test("Audit page separates actor and affected-user autocomplete with debounce", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('label="Executado por"'));
  assert.ok(page.includes('label="Usuário afetado"'));
  assert.ok(page.includes('/audit/users?q=${encodeURIComponent(term)}&limit=20'));
  assert.ok(page.includes("}, 300);"));
  assert.ok(page.includes('query.set("actor_id", actorId)'));
  assert.ok(page.includes('query.set("actor_search", actorSearch.trim())'));
  assert.ok(page.includes('query.set("subject_user_id", subjectUserId)'));
  assert.ok(page.includes('query.set("subject_user_search", subjectUserSearch.trim())'));
});

test("Audit page supports module action source kind and period filters", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('/audit/options'));
  assert.ok(page.includes('<option value="SYSTEM">SYSTEM</option>'));
  assert.ok(page.includes('type="datetime-local"'));
  assert.ok(page.includes("Últimas 24h"));
  assert.ok(page.includes(">7 dias<"));
  assert.ok(page.includes(">30 dias<"));
  assert.ok(page.includes("Limpar filtros"));
  assert.ok(page.includes("event_kind: eventKind"));
});

test("Audit page persists filters in URL and keeps server-side pagination", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("window.history.replaceState"));
  assert.ok(page.includes('query.set("module", module)'));
  assert.ok(page.includes('query.set("correlation_id", correlationId)'));
  assert.ok(page.includes("limit: String(PAGE_SIZE)"));
  assert.ok(page.includes("offset + PAGE_SIZE >= data.total"));
  assert.ok(page.includes("setOffset(Math.max(0, offset - PAGE_SIZE))"));
});

test("Audit page summarizes changes and exposes safe event details without raw JSON", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes(".slice(0, 2)"));
  assert.ok(page.includes("Ver detalhes"));
  assert.ok(page.includes("Snapshot anterior"));
  assert.ok(page.includes("Snapshot posterior"));
  assert.ok(page.includes("Contexto seguro"));
  assert.ok(page.includes("Correlation ID"));
  assert.ok(page.includes("Ver eventos relacionados"));
  assert.ok(!page.includes("JSON.stringify(item.changes"));
  assert.ok(!page.includes("<pre>{"));
});
