import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  normalizeThemePreference,
  parseSidebarCollapsed,
  resolveThemePreference,
  serializeSidebarCollapsed,
  SIDEBAR_STORAGE_KEY,
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
  assert.match(layout, new RegExp(SIDEBAR_STORAGE_KEY.replaceAll(".", "\\.")));
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
  const shell = await readFile(new URL("../components/app-shell.tsx", import.meta.url), "utf8");
  assert.ok(shell.includes('label: "Dashboard"'));
  assert.ok(shell.includes("FINOPS MULTI-CLOUD"));
  assert.ok(!shell.includes("Ambiente protegido"));
  assert.ok(!shell.includes("AWS FinOps"));
  assert.ok(shell.includes("Recolher navegação"));
  assert.ok(shell.includes("Expandir navegação"));
  assert.ok(shell.includes('className="sidebar-tooltip"'));
  assert.ok(shell.includes("serializeSidebarCollapsed"));
  assert.ok(shell.includes('aria-label={mobileOpen ? "Fechar navegação" : "Abrir navegação"}'));
  assert.ok(shell.includes('event.key === "Escape"'));
  assert.ok(!shell.includes("resolveThemePreference"));
  assert.ok(!shell.includes("deepops:theme-change"));
});

test("authentication and metadata no longer present DeepOps as AWS-only", async () => {
  const login = await readFile(new URL("../app/login/page.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.ok(!login.includes("AWS FINOPS INTELLIGENCE"));
  assert.ok(login.includes("FINOPS MULTI-CLOUD"));
  assert.ok(!layout.includes("ambientes AWS"));
  assert.ok(layout.includes("FinOps Multi-Cloud"));
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
