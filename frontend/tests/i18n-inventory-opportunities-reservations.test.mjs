import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import test from "node:test";
import { validateCatalogObjects } from "../scripts/check-i18n.mjs";
import { buildInventoryApiQuery, parseInventorySearchParams } from "../lib/inventory-query.mjs";
import { buildRdsDashboardQuery, parseRdsReservationSearchParams } from "../lib/rds-reservations-query.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = (name) => readFileSync(path.join(ROOT, name), "utf8");
const pt = JSON.parse(source("i18n/messages/pt-BR.json"));
const en = JSON.parse(source("i18n/messages/en-US.json"));

test("Task 25.6 catalogs are ICU-valid, key-parallel and use exactly the official locale mechanism", () => {
  const validation = validateCatalogObjects(pt, en);
  assert.ok(validation.keys > 0);
  for (const namespace of ["inventory", "opportunities", "reservations"]) {
    assert.ok(pt[namespace]);
    assert.deepEqual(Object.keys(pt[namespace]).sort(), Object.keys(en[namespace]).sort());
  }
  for (const name of [
    "app/inventory/page.tsx", "app/opportunities/page.tsx", "app/rds/reservations/page.tsx",
    "components/opportunity-detail.tsx", "components/opportunity-decision-dialog.tsx",
  ]) {
    const page = source(name);
    assert.match(page, /useTranslations/);
    assert.doesNotMatch(page, /navigator\.language/);
  }
});

test("Inventory uses stable presence and lifecycle values but distinct translations", () => {
  assert.equal(pt.inventory.presence.active, "Ativo");
  assert.equal(en.inventory.presence.active, "Active");
  assert.equal(pt.inventory.presence.missing, "Ausente");
  assert.equal(en.inventory.presence.missing, "Missing");
  const state = parseInventorySearchParams(new URLSearchParams("presence_status=missing&provider=oci&sort=last_seen_at"));
  const queryBefore = buildInventoryApiQuery(state);
  assert.equal(queryBefore, buildInventoryApiQuery(state));
  assert.equal(new URLSearchParams(queryBefore).get("presence_status"), "missing");
  assert.equal(new URLSearchParams(queryBefore).get("provider"), "oci");
  const page = source("app/inventory/page.tsx");
  assert.match(page, /resource\.resource_id/);
  assert.match(page, /lifecycleLabel\(resource\.lifecycle_status/);
});

test("Reservation coverage, expiration and normalized units remain domain-owned", () => {
  assert.equal(pt.reservations.coverage.full, "Cobertura total");
  assert.equal(en.reservations.coverage.full, "Fully covered");
  for (const code of ["LE_7", "LE_15", "LE_30", "GT_30", "EXPIRED", "FULL", "PARTIAL", "UNCOVERED", "UNKNOWN"]) {
    assert.ok(source("app/rds/reservations/page.tsx").includes(code));
  }
  const state = parseRdsReservationSearchParams(new URLSearchParams("tab=coverage&account=123&expiration_range=LE_30"));
  const query = buildRdsDashboardQuery(state, "coverage");
  assert.equal(query, buildRdsDashboardQuery(state, "coverage"));
  const page = source("app/rds/reservations/page.tsx");
  for (const term of ["required_units", "covered_units", "formatNu", "useTranslations", "useLocale", "item.days_remaining"]) {
    assert.ok(page.includes(term), "missing capacity or expiration contract: " + term);
  }
});

test("Opportunity decision and history preserve structured technical codes, never translated payload values", () => {
  const decision = source("components/opportunity-decision-dialog.tsx");
  const archive = source("components/opportunity-archive-dialog.tsx");
  const presence = source("components/opportunity-presence-history.tsx");
  const cycles = source("app/opportunities/history-cycles/page.tsx");
  for (const code of ["FALSE_POSITIVE", "OPERATIONAL_EXCEPTION", "ACCEPTABLE_COST", "RESOURCE_REQUIRED", "RISK_ACCEPTED", "OTHER"]) {
    assert.match(decision, new RegExp(code));
  }
  assert.match(decision, /rejectionRequiresNote/);
  assert.match(archive, /JSON\.stringify\(\{ filters, archive_all: archiveAll \}\)/);
  assert.match(archive, /\/opportunities\/period-close/);
  for (const code of ["NOT_OBSERVED_IN_SUCCESSFUL_SCOPE", "MISSING_THRESHOLD_REACHED", "OBSERVED_AGAIN"]) assert.ok(presence.includes(code));
  assert.match(cycles, /historyMoneyRows/);
  assert.match(cycles, /chooseHistoryCycle/);
  assert.match(cycles, /\/opportunity-history\/snapshots/);
});

test("Backend-controlled evidence text and cloud identifiers remain unmodified by localization", () => {
  const evidence = source("components/finding-evidence.tsx");
  const detail = source("components/opportunity-detail.tsx");
  assert.match(evidence, /\{evidence\.summary\}/);
  assert.match(evidence, /\{evidence\.rule\.description\}/);
  assert.match(detail, /copyTechnical\("resource-id", detail\.resource_id\)/);
  assert.match(detail, /copyTechnical\("account-id", detail\.account_id\)/);
  assert.match(detail, /copyTechnical\("opportunity-id", detail\.id\)/);
  assert.notEqual(pt.opportunities.status.open, en.opportunities.status.open);
  assert.equal(pt.opportunities.detail.archiveReason.manual, en.opportunities.detail.archiveReason.manual);
});
