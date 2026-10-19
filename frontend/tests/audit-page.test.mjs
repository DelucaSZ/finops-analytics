import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageUrl = new URL("../app/settings/audit/page.tsx", import.meta.url);

test("Audit page renders unified security and administrative events", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('event_kind: "security" | "administrative"'));
  assert.ok(page.includes('<option value="administrative">Administrativos</option>'));
  assert.ok(page.includes('<option value="security">Segurança</option>'));
  assert.ok(page.includes('item.source === "SYSTEM"'));
  assert.ok(page.includes('item.action === "auth.login_failed"'));
});

test("Audit page summarizes changes without dumping raw JSON", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes("value === null || value === undefined"));
  assert.ok(page.includes(".slice(0, 2)"));
  assert.ok(page.includes("<summary>Ver alterações</summary>"));
  assert.ok(page.includes("Alterações resumidas por limite de tamanho"));
  assert.ok(!page.includes("JSON.stringify(item.changes"));
  assert.ok(!page.includes("<pre>{"));
});

test("Audit page keeps server-side pagination and basic filters", async () => {
  const page = await readFile(pageUrl, "utf8");

  assert.ok(page.includes('event_type: eventType'));
  assert.ok(page.includes('query.set("module", module.trim())'));
  assert.ok(page.includes('query.set("action", action.trim())'));
  assert.ok(page.includes('limit: "50"'));
  assert.ok(page.includes("offset + 50 >= data.total"));
  assert.ok(page.includes("setOffset(Math.max(0, offset - 50))"));
});
