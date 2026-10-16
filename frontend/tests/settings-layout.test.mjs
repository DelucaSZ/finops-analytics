import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const settingsLayoutUrl = new URL("../app/settings/layout.tsx", import.meta.url);
const settingsCssUrl = new URL(
  "../app/settings/settings-layout.module.css",
  import.meta.url,
);
const httpsPageUrl = new URL("../app/settings/https/page.tsx", import.meta.url);
const billingProfilesPageUrl = new URL(
  "../app/settings/billing/profiles/page.tsx",
  import.meta.url,
);

test("Settings layout contains page content without changing navigation semantics", async () => {
  const [layout, css] = await Promise.all([
    readFile(settingsLayoutUrl, "utf8"),
    readFile(settingsCssUrl, "utf8"),
  ]);

  assert.ok(layout.includes('aria-label="Configurações"'));
  assert.ok(layout.includes("styles.page"));
  assert.ok(layout.includes("styles.content"));
  assert.ok(css.includes("max-width: 100%"));
  assert.ok(css.includes("min-width: 0"));
});

test("HTTPS settings keeps controls and technical values inside the viewport", async () => {
  const [page, css] = await Promise.all([
    readFile(httpsPageUrl, "utf8"),
    readFile(settingsCssUrl, "utf8"),
  ]);

  assert.ok(page.includes('className="https-settings-page"'));
  assert.ok(page.includes('className="settings-form-grid"'));
  assert.ok(css.includes(".https-settings-page .settings-form-grid"));
  assert.ok(css.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"));
  assert.ok(css.includes(".https-settings-page .security-card select"));
  assert.ok(css.includes(".https-settings-page .security-card textarea"));
  assert.ok(css.includes("overflow-wrap: anywhere"));

  assert.ok(page.includes('api<TlsStatus>("/tls")'));
  assert.ok(page.includes('api<ValidationResult>("/tls/validate"'));
  assert.ok(page.includes('api<TlsStatus>("/tls/apply"'));
});

test("Billing Profiles uses a shared column contract and internal table scrolling", async () => {
  const [page, css] = await Promise.all([
    readFile(billingProfilesPageUrl, "utf8"),
    readFile(settingsCssUrl, "utf8"),
  ]);

  assert.ok(page.includes('className="billing-profiles-page"'));
  assert.ok(page.includes("<colgroup>"));
  assert.ok(page.includes('className="billing-col-profile"'));
  assert.ok(page.includes('className="billing-col-configuration"'));
  assert.ok(page.includes('className="billing-col-grouping"'));
  assert.ok(page.includes('className="billing-col-status"'));
  assert.ok(page.includes('className="billing-col-actions"'));
  assert.equal((page.match(/scope="col"/g) ?? []).length, 5);
  assert.ok(css.includes(".billing-profiles-table-wrap"));
  assert.ok(css.includes("overflow-x: auto"));
  assert.ok(css.includes("table-layout: fixed"));
  assert.ok(css.includes("min-width: 900px"));

  assert.ok(page.includes("createBillingProfile"));
  assert.ok(page.includes("updateBillingProfile"));
  assert.ok(page.includes("setDefaultBillingProfile"));
  assert.ok(page.includes("deactivateBillingProfile"));
});
