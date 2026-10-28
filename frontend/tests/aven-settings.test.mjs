import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { scanText, summarize } from "../scripts/check-design-system.mjs";

async function source(relativeUrl) {
  return readFile(new URL(relativeUrl, import.meta.url), "utf8");
}

test("Settings shell preserves route-based navigation and uses Aven Tabs", async () => {
  const layout = await source("../app/settings/layout.tsx");
  assert.ok(layout.includes("Tabs"));
  assert.ok(layout.includes("TabsList"));
  assert.ok(layout.includes("TabsTrigger"));
  assert.ok(layout.includes("TabsContent"));
  assert.ok(layout.includes("settingsTabsForRole"));
  assert.ok(layout.includes("router.push(href)"));
  assert.ok(layout.includes("isAdminOnlySettingsPath"));
  assert.ok(!layout.includes('from "next/link"'));
});

test("Settings permission bootstrap is not refetched on every subroute change", async () => {
  const layout = await source("../app/settings/layout.tsx");
  assert.ok(layout.includes('api<CurrentUser>("/auth/me")'));
  assert.match(layout, /\}, \[retry\]\);/);
  assert.doesNotMatch(layout, /\}, \[path,\s*retry\]\);/);
});

test("Appearance reuses the official Theme Engine control", async () => {
  const page = await source("../app/settings/appearance/page.tsx");
  assert.ok(page.includes('from "@/components/aven"'));
  assert.ok(page.includes("<ThemeSelector"));
  assert.ok(!page.includes("localStorage"));
  assert.ok(!page.includes("matchMedia"));
  assert.ok(!page.includes("data-theme"));
});

test("Security preserves real password and reauthentication mutations", async () => {
  const page = await source("../app/settings/security/page.tsx");
  for (const contract of ["/auth/mfa/status", "/auth/change-password", "/auth/reauthenticate"]) {
    assert.ok(page.includes(contract), `missing existing security contract ${contract}`);
  }
  for (const primitive of ["PageHeader", "Section", "Alert", "Button", "Input", "MfaSettings"]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Security settings`);
  }
  assert.ok(page.includes('type="password"'));
  assert.ok(page.includes("router.replace(\"/login\")"));
});

test("Sessions preserves read, revoke and logout-all behavior with Aven Table", async () => {
  const page = await source("../app/settings/sessions/page.tsx");
  assert.ok(page.includes('api<Session[]>("/auth/sessions")'));
  assert.ok(page.includes('api("/auth/logout-all", { method: "POST" })'));
  assert.ok(page.includes('api(`/auth/sessions/${session.id}`, { method: "DELETE" })'));
  for (const primitive of ["PageHeader", "Section", "Alert", "Button", "Table", "TableState"]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Sessions settings`);
  }
});

test("Billing Profiles preserves persisted profile actions on Aven primitives", async () => {
  const page = await source("../app/settings/billing/profiles/page.tsx");
  for (const contract of [
    "listBillingProfiles",
    "createBillingProfile",
    "updateBillingProfile",
    "setDefaultBillingProfile",
    "deactivateBillingProfile",
  ]) assert.ok(page.includes(contract), `missing Billing Profile contract ${contract}`);
  for (const primitive of ["PageHeader", "Section", "Input", "Select", "Checkbox", "Table", "StatusIndicator", "Alert", "Button"]) {
    assert.ok(page.includes(primitive), `expected ${primitive} in Billing Profiles`);
  }
});

test("Settings navigation exposes only audited existing routes", async () => {
  const navigation = await source("../lib/settings-navigation.mjs");
  for (const route of [
    "/settings/appearance",
    "/settings/accounts",
    "/settings/policies",
    "/settings/security",
    "/settings/sessions",
    "/settings/users",
    "/settings/audit",
    "/settings/https",
    "/settings/pricing/oci",
    "/settings/billing/profiles",
    "/settings/usage-costs",
    "/settings/opportunities",
  ]) assert.ok(navigation.includes(route), `missing audited Settings route ${route}`);

  for (const invented of ["notifications", "webhooks", "language", "timezone", "api-tokens"]) {
    assert.ok(!navigation.toLowerCase().includes(invented), `invented Settings navigation item: ${invented}`);
  }
});

test("migrated Settings files pass the Aven hardcode gate independently", async () => {
  const files = [
    ["app/settings/layout.tsx", "../app/settings/layout.tsx"],
    ["app/settings/settings-layout.module.css", "../app/settings/settings-layout.module.css"],
    ["app/settings/settings-page.module.css", "../app/settings/settings-page.module.css"],
    ["app/settings/appearance/page.tsx", "../app/settings/appearance/page.tsx"],
    ["app/settings/security/page.tsx", "../app/settings/security/page.tsx"],
    ["app/settings/sessions/page.tsx", "../app/settings/sessions/page.tsx"],
    ["app/settings/billing/profiles/page.tsx", "../app/settings/billing/profiles/page.tsx"],
  ];
  const entries = await Promise.all(files.map(async ([filename, relativeUrl]) => [filename, await source(relativeUrl)]));
  const violations = entries.flatMap(([filename, content]) => scanText(content, filename));
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
  assert.deepEqual(violations, []);
});

test("Settings migration is included in lint and design-system scopes", async () => {
  const packageJson = await source("../package.json");
  const gate = await source("../scripts/check-design-system.mjs");
  assert.ok(packageJson.includes("--file app/settings/layout.tsx"));
  assert.ok(packageJson.includes("--file app/settings/security/page.tsx"));
  assert.ok(packageJson.includes("--file app/settings/sessions/page.tsx"));
  assert.ok(packageJson.includes("--file app/settings/billing/profiles/page.tsx"));
  assert.ok(gate.includes('path.join(ROOT, "app", "settings")'));
  assert.ok(!gate.includes('path.join(ROOT, "app", "settings", "settings-layout.module.css")'));
  assert.ok(!gate.includes('path.join(ROOT, "app", "settings", "settings-page.module.css")'));
});

test("Settings documentation records the Functional Foundation and invented-feature gates", async () => {
  const docs = await readFile(new URL("../../docs/brand/aven/AVEN_SETTINGS.md", import.meta.url), "utf8");
  for (const phrase of [
    "Functional Foundation Gate",
    "Existing Settings Inventory",
    "Not Implemented Because Functionality Does Not Exist",
    "Mocked settings: 0",
    "Invented APIs: 0",
    "Theme Engine",
    "Task 24.16",
  ]) assert.ok(docs.includes(phrase), `missing Settings documentation contract: ${phrase}`);
});
