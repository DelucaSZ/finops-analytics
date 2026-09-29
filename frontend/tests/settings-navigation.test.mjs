import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import {
  canManageCloudAccounts,
  canManagePolicies,
  canRunCloudAnalysis,
  isAdminOnlySettingsPath,
  isSettingsTabActive,
  legacySettingsRedirects,
  settingsTabsForRole,
} from "../lib/settings-navigation.mjs";
import nextConfig from "../next.config.mjs";

test("accounts and policies live inside settings for every authenticated role", () => {
  for (const role of ["admin", "operator", "viewer"]) {
    const hrefs = settingsTabsForRole(role).map((tab) => tab.href);
    assert.ok(hrefs.includes("/settings/accounts"));
    assert.ok(hrefs.includes("/settings/policies"));
    assert.ok(hrefs.includes("/settings/security"));
    assert.ok(hrefs.includes("/settings/sessions"));
  }
  const viewer = settingsTabsForRole("viewer").map((tab) => tab.href);
  assert.ok(!viewer.includes("/settings/users"));
  assert.ok(!viewer.includes("/settings/audit"));
  assert.ok(!viewer.includes("/settings/https"));
});

test("settings active state supports nested routes without widening admin-only areas", () => {
  assert.equal(isSettingsTabActive("/settings/accounts", "/settings/accounts"), true);
  assert.equal(isSettingsTabActive("/settings/accounts/123", "/settings/accounts"), true);
  assert.equal(isSettingsTabActive("/settings/policies/history", "/settings/policies"), true);
  assert.equal(isSettingsTabActive("/settings/security", "/settings/accounts"), false);
  assert.equal(isAdminOnlySettingsPath("/settings/users/123"), true);
  assert.equal(isAdminOnlySettingsPath("/settings/accounts/123"), false);
  assert.equal(isAdminOnlySettingsPath("/settings/policies"), false);
});

test("frontend action capabilities mirror backend role authorization", () => {
  assert.equal(canManageCloudAccounts("admin"), true);
  assert.equal(canManageCloudAccounts("operator"), false);
  assert.equal(canManageCloudAccounts("viewer"), false);
  assert.equal(canRunCloudAnalysis("admin"), true);
  assert.equal(canRunCloudAnalysis("operator"), true);
  assert.equal(canRunCloudAnalysis("viewer"), false);
  assert.equal(canManagePolicies("admin"), true);
  assert.equal(canManagePolicies("operator"), false);
  assert.equal(canManagePolicies("viewer"), false);
});

test("legacy account and policy routes redirect canonically under settings", async () => {
  assert.deepEqual(await nextConfig.redirects(), legacySettingsRedirects);
  assert.deepEqual(legacySettingsRedirects, [
    { source: "/accounts/:path*", destination: "/settings/accounts/:path*", permanent: false },
    { source: "/policies/:path*", destination: "/settings/policies/:path*", permanent: false },
  ]);
});

test("main navigation no longer duplicates accounts or policies and old page implementations are removed", async () => {
  const shell = await readFile(new URL("../components/app-shell.tsx", import.meta.url), "utf8");
  assert.ok(!shell.includes('href: "/accounts"'));
  assert.ok(!shell.includes('href: "/policies"'));
  await access(new URL("../app/settings/accounts/page.tsx", import.meta.url));
  await access(new URL("../app/settings/policies/page.tsx", import.meta.url));
  await assert.rejects(access(new URL("../app/accounts/page.tsx", import.meta.url)));
  await assert.rejects(access(new URL("../app/policies/page.tsx", import.meta.url)));
});
