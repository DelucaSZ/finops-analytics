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
  assert.match(pageSource, /t\("actions\.reopenOpportunity"\)/);
  assert.match(pageSource, /<Dialog/);
  assert.match(pageSource, /<DialogTitle>\{t\("actions\.reopenOpportunity"\)\}<\/DialogTitle>/);
  assert.match(pageSource, /t\("actions\.reopenDescription"\)/);
  assert.match(pageSource, /t\("actions\.reopenDescription"\)/);
  assert.match(pageSource, /t\("actions\.reopenDescription"\)/);
  assert.doesNotMatch(pageSource, /window\.confirm/);
});

test("archived rejected detail uses reopen and explains persistent suppression", () => {
  assert.match(detailSource, /detail\.status === "rejected"/);
  assert.match(detailSource, /`\/opportunities\/\$\{detail\.id\}\/reopen`/);
  assert.match(detailSource, /t\("actions\.reopenOpportunity"\)/);
  assert.match(detailSource, /<Dialog/);
  assert.match(detailSource, /<DialogTitle>/);
  assert.match(detailSource, /<DialogDescription>/);
  assert.match(detailSource, /t\("actions\.reopenDescription"\)/);
  assert.match(detailSource, /t\("actions\.reopenDescription"\)/);
  assert.match(detailSource, /t\("actions\.reopenDescription"\)/);
  assert.match(detailSource, /t\("rejectedActiveDescription"\)/);
  assert.doesNotMatch(detailSource, /window\.confirm/);
});
