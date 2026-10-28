import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const layoutSource = readFileSync(new URL("../app/layout.tsx", import.meta.url), "utf8");
const taskCss = readFileSync(new URL("../app/task-23-25-layout.css", import.meta.url), "utf8");
const opportunitiesSource = readFileSync(
  new URL("../app/opportunities/page.tsx", import.meta.url),
  "utf8",
);
const detailSource = readFileSync(
  new URL("../components/opportunity-detail.tsx", import.meta.url),
  "utf8",
);

test("task 23.25 layout overrides are loaded after shared styles", () => {
  assert.match(layoutSource, /import "\.\/task-23-25-layout\.css";/);
  assert.ok(
    layoutSource.indexOf('import "./task-23-25-layout.css";') >
      layoutSource.indexOf('import "./dashboard-operational-insights.css";'),
  );
});

test("dashboard ranked lists keep long labels inside responsive containers", () => {
  assert.match(taskCss, /\.dashboard-ranked-list > a > span \{/);
  assert.match(taskCss, /grid-template-columns: 18px minmax\(0, 1fr\)/);
  assert.match(taskCss, /overflow-wrap: anywhere/);
  assert.match(taskCss, /\.dashboard-distributions \{/);
  assert.match(taskCss, /repeat\(auto-fit, minmax\(min\(13rem, 100%\), 1fr\)\)/);
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
