import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  SCHEDULE_INTERVAL_OPTIONS,
  scheduleIntervalLabel,
  scheduleSummary,
} from "../lib/account-scheduling.mjs";

const baseAccount = {
  schedule_enabled: false,
  scan_interval_hours: 24,
};

const supported = { scheduling: true };
const unsupported = { scheduling: false };

test("scheduling exposes only the supported 12/24/168 hour intervals", () => {
  assert.deepEqual(
    SCHEDULE_INTERVAL_OPTIONS,
    [
      { value: 12, label: "A cada 12 horas" },
      { value: 24, label: "Diariamente" },
      { value: 168, label: "Semanalmente" },
    ],
  );
  assert.equal(scheduleIntervalLabel(12), "A cada 12 horas");
  assert.equal(scheduleIntervalLabel(24), "Diariamente");
  assert.equal(scheduleIntervalLabel(168), "Semanalmente");
});

test("summary is capability-driven and provider-neutral", () => {
  assert.equal(scheduleSummary(baseAccount, unsupported), "Não implementado");
  assert.equal(scheduleSummary(baseAccount, supported), "Desativado");
  assert.equal(scheduleSummary({ ...baseAccount, schedule_enabled: true, scan_interval_hours: 12 }, supported), "A cada 12 horas");
  assert.equal(scheduleSummary({ ...baseAccount, schedule_enabled: true, scan_interval_hours: 24 }, supported), "Diariamente");
  assert.equal(scheduleSummary({ ...baseAccount, schedule_enabled: true, scan_interval_hours: 168 }, supported), "Semanalmente");
});

test("AWS and OCI page use one shared capability-gated scheduling component", async () => {
  const page = await readFile(new URL("../app/settings/accounts/page.tsx", import.meta.url), "utf8");
  const component = await readFile(new URL("../components/collection-schedule-fields.tsx", import.meta.url), "utf8");

  assert.match(page, /<CollectionScheduleFields/);
  assert.match(page, /supported=\{formCapability\?\.scheduling === true\}/);
  assert.match(page, /scheduleEnabled=\{form\.schedule_enabled\}/);
  assert.match(page, /scanIntervalHours=\{form\.scan_interval_hours\}/);
  assert.match(page, /editingAccount\?\.next_scan_at/);
  assert.doesNotMatch(page, /form\.aws\.schedule_enabled/);
  assert.doesNotMatch(page, /form\.aws\.scan_interval_hours/);
  assert.doesNotMatch(component, /isAws|isOci|provider ===/);
  assert.match(component, /Ativar coleta automática/);
  assert.match(component, /Próxima execução prevista/);
  assert.match(component, /Coleta automática desativada/);
  assert.match(component, /Não implementado para este provider/);
});

test("scheduling UI only displays backend-owned next_scan_at", async () => {
  const component = await readFile(new URL("../components/collection-schedule-fields.tsx", import.meta.url), "utf8");
  const page = await readFile(new URL("../app/settings/accounts/page.tsx", import.meta.url), "utf8");

  assert.match(component, /formatDate\(nextScanAt\)/);
  assert.doesNotMatch(component, /Date\.now|new Date|setHours|setTime/);
  assert.match(page, /nextScanAt=\{mode === "edit" \? editingAccount\?\.next_scan_at : null\}/);
});

test("OCI scheduling UI does not receive OCI credentials or configuration", async () => {
  const page = await readFile(new URL("../app/settings/accounts/page.tsx", import.meta.url), "utf8");
  const schedulingCall = page.slice(page.indexOf("<CollectionScheduleFields"), page.indexOf("<div className=\"form-actions", page.indexOf("<CollectionScheduleFields")));

  assert.doesNotMatch(schedulingCall, /oci_configuration|private_key_pem|private_key_password|fingerprint|scope_regions|compartment_ocids/);
});
