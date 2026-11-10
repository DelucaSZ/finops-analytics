import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createTranslator } from "next-intl";
import { validateCatalogObjects } from "../scripts/check-i18n.mjs";
import { settingsTabsForRole, isAdminOnlySettingsPath, canRunCloudAnalysis } from "../lib/settings-navigation.mjs";
import { SCHEDULE_INTERVAL_OPTIONS } from "../lib/account-scheduling.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => readFileSync(path.join(ROOT, file), "utf8");
const pt = JSON.parse(read("i18n/messages/pt-BR.json"));
const en = JSON.parse(read("i18n/messages/en-US.json"));

test("Task 25.7 translations use the official parallel ICU catalogs", () => {
  assert.ok(validateCatalogObjects(pt, en).keys > 0);
  for (const namespace of ["settings", "collections", "scans"]) {
    assert.deepEqual(Object.keys(pt[namespace]).sort(), Object.keys(en[namespace]).sort());
  }
  for (const [locale, dictionary, expected] of [
    ["pt-BR", pt, "Agendamento"],
    ["en-US", en, "Scheduling"],
  ]) {
    const t = createTranslator({locale, messages:dictionary, namespace:"settings"});
    assert.equal(t("schedule.title"), expected);
    assert.ok(t("appearance.description", {product:"Aven"}).includes("Aven"));
  }
  assert.equal(createTranslator({locale:"en-US", messages:en, namespace:"collections"})("manual.success", {account:"AWS Test"}), "Collection for AWS Test requested successfully.");
});

test("Settings navigation labels cannot affect route, permission or role checks", () => {
  const admin = settingsTabsForRole("admin");
  const viewer = settingsTabsForRole("viewer");
  assert.equal(admin.length, 12);
  assert.equal(viewer.length, 5);
  for (const tab of admin) {
    assert.ok(tab.href.startsWith("/settings/"));
    assert.ok(tab.labelKey);
    assert.ok(pt.settings.navigation[tab.labelKey]);
    assert.ok(en.settings.navigation[tab.labelKey]);
  }
  assert.equal(isAdminOnlySettingsPath("/settings/users"), true);
  assert.equal(isAdminOnlySettingsPath("/settings/security"), false);
  assert.equal(canRunCloudAnalysis("admin"), true);
  assert.equal(canRunCloudAnalysis("viewer"), false);
});

test("Security, sessions and collection scheduling preserve technical contracts", () => {
  const security = read("app/settings/security/page.tsx");
  const sessions = read("app/settings/sessions/page.tsx");
  const schedule = read("components/collection-schedule-fields.tsx");
  const manual = read("components/manual-collection-launcher.tsx");
  for (const route of ["/auth/change-password", "/auth/reauthenticate", "/auth/mfa/status"]) assert.ok(security.includes(route));
  for (const route of ["/auth/sessions", "/auth/logout-all"]) assert.ok(sessions.includes(route));
  assert.deepEqual(SCHEDULE_INTERVAL_OPTIONS.map(x => x.value), [12, 24, 168]);
  assert.match(schedule, /value: String\(option.value\)/);
  assert.match(schedule, /onIntervalChange\(Number\(event.target.value\)\)/);
  assert.match(manual, /\/cloud-accounts\/\$\{selected.id\}\/scans/);
  assert.match(manual, /canRunCloudAnalysis\(role\)/);
  assert.match(manual, /invalidateApiQueries\(queryKeys.collections.all\)/);
});

test("Scans presentation translates status without changing API status codes or links", () => {
  const scans = read("app/scans/page.tsx");
  for (const code of ["SUCCESS", "COMPLETED", "FAILED", "ERROR", "RUNNING", "PENDING", "COMPLETED_WITH_WARNINGS"]) assert.ok(scans.includes(code));
  assert.match(scans, /statusPresentation\(scan.status, labels\)/);
  assert.match(scans, /\/collections\/\$\{run.id\}\/compare/);
  assert.notEqual(pt.scans.status.running, en.scans.status.running);
});
