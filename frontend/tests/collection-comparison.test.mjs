import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("collection comparison is backend-owned, paginated and shareable", async () => {
  const page = await readFile(
    new URL("../app/collections/[collectionId]/compare/page.tsx", import.meta.url),
    "utf8",
  );
  const types = await readFile(new URL("../lib/types.ts", import.meta.url), "utf8");

  assert.match(page, /\/collections\/\$\{collectionId\}\/compare\?/);
  assert.match(page, /comparison-options/);
  assert.match(page, /baseline_id/);
  assert.match(page, /category/);
  assert.match(page, /page_size/);
  assert.match(page, /NEW/);
  assert.match(page, /PERSISTENT/);
  assert.match(page, /NO_LONGER_DETECTED/);
  assert.match(page, /CHANGED/);
  assert.match(page, /Não detectadas/);
  assert.match(page, /rules_version_warning/);
  assert.match(page, /financial_summary/);
  assert.match(page, /lifecycle_status/);
  assert.match(page, /opportunity_id/);
  assert.doesNotMatch(page, /OpportunityObservation\[\]/);

  assert.match(types, /CollectionComparisonResponse/);
  assert.match(types, /CollectionComparisonCategory/);
  assert.match(types, /rules_version/);
});

test("execution history exposes CollectionRun detail and comparison navigation", async () => {
  const scans = await readFile(new URL("../app/scans/page.tsx", import.meta.url), "utf8");
  const detail = await readFile(
    new URL("../app/collections/[collectionId]/page.tsx", import.meta.url),
    "utf8",
  );

  assert.match(scans, /\/collections\?limit=200/);
  assert.match(scans, /Ver coleta/);
  assert.match(scans, /Comparar/);
  assert.match(detail, /comparison-options/);
  assert.match(detail, /runData\.status === "SUCCESS"/);
  assert.match(detail, /Comparar com coleta anterior/);
  assert.match(detail, /primeira coleta bem-sucedida/);
});
