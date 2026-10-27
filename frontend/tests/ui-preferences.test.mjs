import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  normalizeThemePreference,
  parseSidebarCollapsed,
  resolveThemePreference,
  serializeSidebarCollapsed,
  THEME_STORAGE_KEY,
} from "../lib/ui-preferences.mjs";

test("theme preference defaults to system, preserves explicit choices and migrates legacy booleans", () => {
  assert.equal(normalizeThemePreference(null), "system");
  assert.equal(normalizeThemePreference("unknown"), "system");
  assert.equal(normalizeThemePreference("SYSTEM"), "system");
  assert.equal(normalizeThemePreference("light"), "light");
  assert.equal(normalizeThemePreference("dark"), "dark");
  assert.equal(normalizeThemePreference(true), "dark");
  assert.equal(normalizeThemePreference(false), "light");
  assert.equal(normalizeThemePreference("true"), "dark");
  assert.equal(normalizeThemePreference("false"), "light");
});

test("system theme follows the operating system while explicit themes do not", () => {
  assert.equal(resolveThemePreference("system", false), "light");
  assert.equal(resolveThemePreference("system", true), "dark");
  assert.equal(resolveThemePreference("light", true), "light");
  assert.equal(resolveThemePreference("dark", false), "dark");
});

test("sidebar persistence is strict and has an expanded fallback", () => {
  assert.equal(parseSidebarCollapsed(null), false);
  assert.equal(parseSidebarCollapsed("false"), false);
  assert.equal(parseSidebarCollapsed("invalid"), false);
  assert.equal(parseSidebarCollapsed("true"), true);
  assert.equal(serializeSidebarCollapsed(false), "false");
  assert.equal(serializeSidebarCollapsed(true), "true");
});

test("layout bootstraps appearance before hydration and mounts the centralized theme provider", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.ok(layout.includes("getThemeBootstrapScript"));
  assert.ok(layout.includes("JSON.stringify(SIDEBAR_STORAGE_KEY)"));
  assert.ok(layout.includes("<ThemeProvider>"));
  assert.ok(layout.includes("<AppShell>{children}</AppShell>"));
});

test("theme selector delegates preference state and mutation to useTheme", async () => {
  const selector = await readFile(new URL("../components/theme-selector.tsx", import.meta.url), "utf8");
  assert.ok(selector.includes("useTheme"));
  assert.ok(selector.includes("const { theme, setTheme } = useTheme()"));
  assert.ok(selector.includes("setTheme(option.value)"));
  assert.ok(!selector.includes("localStorage"));
  assert.ok(!selector.includes("matchMedia"));
});

test("global shell is provider-neutral and exposes accessible persistent collapse behavior", async () => {
  const [rootShell, visualShell, navigation] = await Promise.all([
    readFile(new URL("../components/app-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/app-shell/application-shell.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/app-shell/navigation.ts", import.meta.url), "utf8"),
  ]);
  const shellContract = `${visualShell}\n${navigation}`;

  assert.ok(navigation.includes('label: "Dashboard"'));
  assert.ok(navigation.includes('label: "Fluxo"'));
  assert.ok(!shellContract.includes("Ambiente protegido"));
  assert.ok(!shellContract.includes("AWS FinOps"));
  assert.ok(visualShell.includes("Recolher navegação"));
  assert.ok(visualShell.includes("Expandir navegação"));
  assert.ok(visualShell.includes("<Tooltip"));
  assert.ok(visualShell.includes("serializeSidebarCollapsed"));
  assert.ok(visualShell.includes('aria-label="Abrir navegação"'));
  assert.ok(visualShell.includes("<Drawer open={mobileOpen}"));
  assert.ok(visualShell.includes("onOpenChange={setMobileOpen}"));
  assert.ok(!rootShell.includes("resolveThemePreference"));
  assert.ok(!rootShell.includes("deepops:theme-change"));
});

test("authentication and metadata use provider-neutral Aven identity", async () => {
  const [login, authLayout, layout, brand] = await Promise.all([
    readFile(new URL("../app/login/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/auth/auth-layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../lib/brand.ts", import.meta.url), "utf8"),
  ]);
  const authExperience = `${login}\n${authLayout}`;
  assert.ok(!authExperience.includes("AWS FINOPS INTELLIGENCE"));
  assert.ok(authLayout.includes("FINOPS MULTI-CLOUD"));
  assert.ok(!layout.includes("ambientes AWS"));
  assert.ok(layout.includes("brand.description"));
  assert.ok(brand.includes("FinOps Multi-Cloud"));
  assert.ok(brand.includes('PRODUCT_NAME = "Aven"'));
});

test("semantic design tokens cover both themes, charts, focus, responsive navigation and reduced motion", async () => {
  const css = await readFile(new URL("../app/ui-system.css", import.meta.url), "utf8");
  for (const token of [
    "--background:",
    "--foreground:",
    "--surface:",
    "--border:",
    "--primary:",
    "--success:",
    "--warning:",
    "--danger:",
    "--chart-1:",
    "--sidebar-expanded-width:",
    "--sidebar-collapsed-width:",
  ]) assert.ok(css.includes(token), `missing token ${token}`);
  assert.ok(css.includes('html[data-theme="dark"]'));
  assert.ok(css.includes('html[data-sidebar="collapsed"]'));
  assert.ok(css.includes("@media (max-width: 900px)"));
  assert.ok(css.includes("@media (prefers-reduced-motion: reduce)"));
  assert.ok(css.includes(".sidebar-overlay.visible"));
});

test("human lifecycle and technical presence badges remain visually distinct", async () => {
  const badge = await readFile(new URL("../components/status-badge.tsx", import.meta.url), "utf8");
  const compat = await readFile(new URL("../app/legacy-theme-compat.css", import.meta.url), "utf8");
  assert.ok(badge.includes('const humanStatuses = new Set(["open", "treated", "rejected"])'));
  assert.ok(badge.includes('const presenceStatuses = new Set(["active", "missing", "resolved_externally"])'));
  assert.ok(badge.includes("data-status-kind={kind}"));
  assert.ok(compat.includes(".presence-status-badge"));
  assert.ok(compat.includes(".human-status-badge"));
});
