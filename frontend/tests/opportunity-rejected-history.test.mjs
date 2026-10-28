import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageSource = await readFile(
  new URL("../app/opportunities/page.tsx", import.meta.url),
  "utf8",
);
const detailSource = await readFile(
  new URL("../components/opportunity-detail.tsx", import.meta.url),
  "utf8",
);

test("historical rejected rows require Aven confirmation before reopen", () => {
  assert.match(pageSource, /finding\.status === "rejected"/);
  assert.match(pageSource, /setRestoreHistoryFinding\(finding\)/);
  assert.match(pageSource, /confirmRejectedHistoryReopen/);
  assert.match(pageSource, /`\/opportunities\/\$\{finding\.id\}\/reopen`/);
  assert.match(pageSource, /`\/opportunities\/\$\{finding\.id\}\/unarchive`/);
  assert.match(pageSource, /Reabrir oportunidade/);
  assert.match(pageSource, /<Dialog/);
  assert.match(pageSource, /<DialogTitle>Reabrir oportunidade<\/DialogTitle>/);
  assert.match(pageSource, /decisão de rejeição será removida/i);
  assert.match(pageSource, /voltará ao backlog operacional/i);
  assert.match(pageSource, /histórico permanecerá registrado/i);
  assert.doesNotMatch(pageSource, /window\.confirm/);
});

test("archived rejected detail uses reopen and explains persistent suppression", () => {
  assert.match(detailSource, /detail\.status === "rejected"/);
  assert.match(detailSource, /`\/opportunities\/\$\{detail\.id\}\/reopen`/);
  assert.match(detailSource, /Reabrir oportunidade/);
  assert.match(detailSource, /<Dialog/);
  assert.match(detailSource, /<DialogTitle>/);
  assert.match(detailSource, /<DialogDescription>/);
  assert.match(detailSource, /decisão de rejeição será removida/i);
  assert.match(detailSource, /voltará ao backlog operacional/i);
  assert.match(detailSource, /histórico permanecerá registrado/i);
  assert.match(detailSource, /recomendação permanece suprimida pela decisão humana registrada/i);
  assert.doesNotMatch(detailSource, /window\.confirm/);
});
