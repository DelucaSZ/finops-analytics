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

test("theme preference defaults to system and preserves explicit choices", () => {
  assert.equal(normalizeThemePreference(null), "system");
  assert.equal(normalizeThemePreference("unknown"), "system");
  assert.equal(normalizeThemePreference("SYSTEM"), "system");
  assert.equal(normalizeThemePreference("light"), "light");
  assert.equal(normalizeThemePreference("dark"), "dark");
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

test("layout bootstraps appearance before hydration and keeps preference keys stable", async () => {
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.match(layout, new RegExp(THEME_STORAGE_KEY.replaceAll(".", "\\.")));
  assert.match(layout, new RegExp(SIDEBAR_STORAGE_KEY.replaceAll(".", "\\.")));
  assert.ok(layout.includes('matchMedia("(prefers-color-scheme: dark)")'));
  assert.ok(layout.includes('root.dataset.theme = resolved'));
  assert.ok(layout.includes('root.dataset.sidebar = collapsed ? "collapsed" : "expanded"'));
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
});

test("authentication and metadata no longer present DeepOps as AWS-only", async () => {
  const login = await readFile(new URL("../app/login/page.tsx", import.meta.url), "utf8");
  const layout = await readFile(new URL("../app/layout.tsx", import.meta.url), "utf8");
  assert.ok(!login.includes("AWS FINOPS INTELLIGENCE"));
  assert.ok(login.includes("FINOPS MULTI-CLOUD"));
  assert.ok(!layout.includes("ambientes AWS"));
  assert.ok(layout.includes("FinOps Multi-Cloud"));
});
