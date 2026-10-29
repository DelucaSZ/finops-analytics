import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

const layoutSource = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const legacyTaskCssUrl = new URL("../app/task-23-25-layout.css", import.meta.url);
const opportunitiesSource = readFileSync(
  new URL("../app/opportunities/page.tsx", import.meta.url),
  "utf8",
);
const detailSource = readFileSync(
  new URL("../components/opportunity-detail.tsx", import.meta.url),
  "utf8",
);

test("obsolete Task 23.25 layout patch stays retired after the Aven migrations", () => {
  assert.equal(existsSync(legacyTaskCssUrl), false);
  assert.doesNotMatch(layoutSource, /task-23-25-layout\.css/);
});

test("opportunity detection timestamps remain explicit in the Aven surface", () => {
  assert.match(opportunitiesSource, /Primeira identificação/);
  assert.match(opportunitiesSource, /Última detecção/);
  assert.match(detailSource, /<dt>Primeira identificação<\/dt><dd>\{formatDate\(detail\.first_seen_at\)\}/);
  assert.match(detailSource, /<dt>Última detecção<\/dt><dd>\{formatDate\(detail\.last_seen_at\)\}/);
});

test("opportunity detail keeps collection references linked without legacy CSS hooks", () => {
  assert.match(detailSource, /Abrir primeira coleta/i);
  assert.match(detailSource, /Abrir última coleta/i);
  assert.match(detailSource, /href=\{`\/collections\/\$\{encodeURIComponent\(detail\.first_seen_collection_run_id\)\}`\}/);
  assert.match(detailSource, /href=\{`\/collections\/\$\{encodeURIComponent\(detail\.last_seen_collection_run_id\)\}`\}/);
});
