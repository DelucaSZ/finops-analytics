import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SHELL = path.join(ROOT, "components", "app-shell");
const ROOT_SHELL = path.join(ROOT, "components", "app-shell.tsx");
const read = (name) => fs.readFileSync(path.join(SHELL, name), "utf8");

test("Aven Application Shell exposes the required architecture", () => {
  for (const file of ["application-shell.tsx", "navigation.ts", "app-shell.module.css"]) {
    assert.ok(fs.existsSync(path.join(SHELL, file)), `${file} should exist`);
  }
  const source = read("application-shell.tsx");
  assert.match(source, /function Sidebar\(/);
  assert.match(source, /function Topbar\(/);
  assert.match(source, /export function ApplicationShell\(/);
  assert.match(source, /<aside/);
  assert.match(source, /<header/);
  assert.match(source, /<main/);
});

test("navigation preserves the current product destinations in one shared configuration", () => {
  const navigation = read("navigation.ts");
  for (const route of [
    "\"/\"",
    "\"/opportunities\"",
    "\"/opportunities/history-cycles\"",
    "\"/flow\"",
    "\"/billing\"",
    "\"/rds/reservations\"",
    "\"/collections\"",
    "\"/settings\"",
  ]) assert.match(navigation, new RegExp(route.replaceAll("/", "\\/")));

  const shell = read("application-shell.tsx");
  assert.match(shell, /navigation\.map/);
  assert.match(shell, /<SidebarNavigation pathname=\{pathname\} collapsed=\{collapsed\}/);
  assert.match(shell, /<SidebarNavigation[\s\S]*collapsed=\{false\}/);
});

test("active route logic handles exact roots and nested feature routes without prefix collisions", () => {
  const source = read("navigation.ts");
  assert.match(source, /pathname === item\.href/);
  assert.match(source, /activePrefixes\?\.some/);
  assert.match(source, /pathname\.startsWith\(`\$\{item\.href\}\/`\)/);
  assert.match(source, /activePrefixes: \["\/opportunities\/collection\/"\]/);
});

test("desktop collapse is persisted independently from the Theme Engine", () => {
  const source = read("application-shell.tsx");
  assert.match(source, /SIDEBAR_STORAGE_KEY/);
  assert.match(source, /parseSidebarCollapsed/);
  assert.match(source, /serializeSidebarCollapsed/);
  assert.match(source, /document\.documentElement\.dataset\.sidebar/);
  assert.doesNotMatch(source, /THEME_STORAGE_KEY|persistThemePreference|resolveThemePreference/);
});

test("topbar theme control delegates Light Dark System to useTheme", () => {
  const source = read("application-shell.tsx");
  assert.match(source, /useTheme\(\)/);
  assert.match(source, /value: "light"/);
  assert.match(source, /value: "dark"/);
  assert.match(source, /value: "system"/);
  assert.match(source, /setTheme\(option\.value\)/);
  assert.doesNotMatch(source, /localStorage.*theme|matchMedia/);
});

test("mobile navigation reuses Drawer and the same navigation tree", () => {
  const source = read("application-shell.tsx");
  assert.match(source, /<Drawer open=\{mobileOpen\}/);
  assert.match(source, /<DrawerContent side="left"/);
  assert.match(source, /setMobileOpen\(false\)/);
  assert.match(source, /onNavigate=\{\(\) => setMobileOpen\(false\)\}/);
});

test("user menu preserves the existing logout callback while showing only real session data", () => {
  const visual = read("application-shell.tsx");
  const root = fs.readFileSync(ROOT_SHELL, "utf8");
  assert.match(visual, /onClick=\{\(\) => void onLogout\(\)\}/);
  assert.match(visual, /Avatar fallback=\{initials\}/);
  assert.match(root, /api\("\/auth\/logout", \{ method: "POST" \}\)/);
  assert.match(root, /clearApiQueryCache\(\)/);
  assert.match(root, /router\.replace\("\/login"\)/);
  assert.doesNotMatch(visual, /fetch\(|api\(/);
});

test("authentication gate preserves public routes and current session compatibility behavior", () => {
  const source = fs.readFileSync(ROOT_SHELL, "utf8");
  for (const route of ["/mfa-setup", "/login", "/forgot-password", "/reset-password", "/accept-invitation"]) {
    assert.match(source, new RegExp(route.replaceAll("/", "\\/")));
  }
  assert.match(source, /api<ShellUser>\("\/auth\/me", \{\}, false\)/);
  assert.match(source, /deepops:session-invalidated/);
  assert.match(source, /removeItem\("nuvemiq_token"\)/);
});

test("shell exposes navigation accessibility and current-page semantics", () => {
  const source = read("application-shell.tsx");
  assert.match(source, /aria-current=\{active \? "page" : undefined\}/);
  assert.match(source, /aria-label="Navegação principal"/);
  assert.match(source, /href="#main-content"/);
  assert.match(source, /aria-label="Abrir navegação"/);
  assert.match(source, /aria-label="Menu do usuário"/);
});

test("shell owns the main scroll container and keeps persistent navigation outside it", () => {
  const styles = read("app-shell.module.css");
  assert.match(styles, /\.shell[\s\S]*overflow: hidden/);
  assert.match(styles, /\.mainContent[\s\S]*overflow: auto/);
  assert.match(styles, /\.navigation[\s\S]*overflow-y: auto/);
  assert.match(styles, /@media \(max-width: 850px\)/);
});

test("hardcode gate is zero for all new and refactored shell sources", () => {
  const violations = [
    ...scanDirectory(ROOT_SHELL),
    ...scanDirectory(SHELL),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
});

test("shell geometry and surfaces are tokenized in the shared component-token layer", () => {
  const tokens = fs.readFileSync(path.join(ROOT, "app", "styles", "tokens", "components.css"), "utf8");
  for (const token of [
    "--shell-sidebar-inline-size",
    "--shell-sidebar-collapsed-inline-size",
    "--shell-topbar-block-size",
    "--shell-page-gutter",
    "--topbar-background",
    "--topbar-border",
  ]) assert.match(tokens, new RegExp(token));
});

test("official application-shell documentation and README integration exist", () => {
  const docs = path.resolve(ROOT, "..", "docs", "brand", "aven");
  assert.ok(fs.existsSync(path.join(docs, "AVEN_APPLICATION_SHELL.md")));
  const readme = fs.readFileSync(path.join(docs, "README.md"), "utf8");
  assert.match(readme, /Aven Application Shell/);
});
