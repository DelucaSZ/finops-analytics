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

test("opportunity detections use vertical label and timestamp blocks", () => {
  assert.match(opportunitiesSource, /className="detection-cell"/);
  assert.match(opportunitiesSource, /<strong>Primeira identificação<\/strong>/);
  assert.match(opportunitiesSource, /<strong>Última detecção<\/strong>/);
  assert.match(taskCss, /\.detection-cell > span \{/);
  assert.match(taskCss, /flex-direction: column/);
  assert.match(taskCss, /white-space: normal/);
});

test("opportunity detail separates collection references from timestamps", () => {
  assert.match(detailSource, /className="collection-link"/);
  assert.match(detailSource, /Primeira coleta/);
  assert.match(detailSource, /Última coleta/);
  assert.match(taskCss, /\.detail-grid dd > \.collection-link \{/);
  assert.match(taskCss, /display: block/);
  assert.match(taskCss, /margin-top: 3px/);
});
