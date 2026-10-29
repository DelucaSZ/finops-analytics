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

test("Settings layout preserves route navigation through the official Aven Tabs contract", async () => {
  const [layout, css] = await Promise.all([
    readFile(settingsLayoutUrl, "utf8"),
    readFile(settingsCssUrl, "utf8"),
  ]);

  for (const primitive of ["Tabs", "TabsList", "TabsTrigger", "TabsContent"]) {
    assert.ok(layout.includes(primitive), `expected ${primitive} in Settings layout`);
  }
  assert.ok(layout.includes('aria-label="Áreas de Configurações"'));
  assert.ok(layout.includes("settingsTabsForRole"));
  assert.ok(layout.includes("isSettingsTabActive"));
  assert.ok(layout.includes("router.push(href)"));
  assert.ok(layout.includes("styles.page"));
  assert.ok(layout.includes("styles.content"));

  assert.ok(css.includes("max-inline-size: 100%"));
  assert.ok(css.includes("min-inline-size: 0"));
  assert.ok(css.includes("overflow-x: auto"));
});

test("HTTPS settings preserves its functional TLS contracts under the tokenized compatibility bridge", async () => {
  const [page, css] = await Promise.all([
    readFile(httpsPageUrl, "utf8"),
    readFile(settingsCssUrl, "utf8"),
  ]);

  assert.ok(page.includes('className="https-settings-page"'));
  assert.ok(page.includes('className="settings-form-grid"'));
  assert.ok(css.includes(".content :global(.settings-form-grid)"));
  assert.ok(css.includes("grid-template-columns: repeat(2, minmax(0, 1fr))"));
  assert.ok(css.includes(".content :global(.security-card select:not([data-aven-control-inner]))"));
  assert.ok(css.includes(".content :global(.security-card textarea:not([data-aven-control-inner]))"));
  assert.ok(css.includes("var(--control-background)"));
  assert.ok(css.includes("var(--control-border)"));
  assert.ok(css.includes("overflow-wrap: anywhere"));

  assert.ok(page.includes('api<TlsStatus>("/tls")'));
  assert.ok(page.includes('api<ValidationResult>("/tls/validate"'));
  assert.ok(page.includes('api<TlsStatus>("/tls/apply"'));
  assert.ok(page.includes("server_certificate:"));
  assert.ok(page.includes("intermediate_chain:"));
  assert.ok(page.includes("Certificado do servidor (PEM)"));
  assert.ok(page.includes("Cadeia intermediária / CA Bundle (PEM)"));
  assert.ok(page.includes("TLS local válido"));
  assert.ok(page.includes("Validação do endpoint"));
  assert.ok(page.includes("A:"));
  assert.ok(page.includes("AAAA:"));
  assert.equal(page.includes("certificate_chain:"), false);
  assert.equal(page.includes('"HTTPS válido"'), false);
});

test("Billing Profiles uses official Aven table/status primitives while preserving persistence actions", async () => {
  const page = await readFile(billingProfilesPageUrl, "utf8");

  for (const primitive of [
    "PageHeader",
    "Section",
    "Table",
    "TableHeader",
    "TableHead",
    "TableBody",
    "TableCell",
    "TableState",
    "StatusIndicator",
    "Button",
  ]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Billing Profiles`);
  }

  assert.ok(page.includes('aria-label="Perfis de Billing disponíveis"'));
  assert.equal((page.match(/<TableHead>/g) ?? []).length, 5);
  assert.equal(page.includes("<colgroup>"), false);
  assert.equal(page.includes('className="billing-profiles-page"'), false);
  assert.equal(page.includes("billing-col-profile"), false);
  assert.equal(page.includes("billing-col-configuration"), false);
  assert.equal(page.includes("billing-col-grouping"), false);
  assert.equal(page.includes("billing-col-status"), false);
  assert.equal(page.includes("billing-col-actions"), false);

  assert.ok(page.includes("createBillingProfile"));
  assert.ok(page.includes("updateBillingProfile"));
  assert.ok(page.includes("setDefaultBillingProfile"));
  assert.ok(page.includes("deactivateBillingProfile"));
});
