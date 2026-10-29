import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const FRONTEND_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");

const readFrontend = (relativePath) => fs.readFileSync(path.join(FRONTEND_ROOT, relativePath), "utf8");
const readRepo = (relativePath) => fs.readFileSync(path.join(REPO_ROOT, relativePath), "utf8");

function collectPageRoutes(directory, relative = "") {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    const child = path.join(relative, entry.name);
    if (entry.isDirectory()) return collectPageRoutes(absolute, child);
    if (entry.name !== "page.tsx") return [];
    const routePath = relative ? `/${relative.split(path.sep).join("/")}` : "/";
    return [routePath];
  });
}

const expectedRoutes = [
  "/",
  "/accept-invitation",
  "/billing",
  "/collections",
  "/collections/[collectionId]",
  "/collections/[collectionId]/compare",
  "/dev/ui",
  "/finops/ledger",
  "/flow",
  "/forgot-password",
  "/inventory",
  "/login",
  "/mfa-setup",
  "/opportunities",
  "/opportunities/collection/[collectionId]",
  "/opportunities/history-cycles",
  "/rds/reservations",
  "/reset-password",
  "/scans",
  "/security",
  "/settings",
  "/settings/accounts",
  "/settings/appearance",
  "/settings/audit",
  "/settings/billing/profiles",
  "/settings/https",
  "/settings/opportunities",
  "/settings/policies",
  "/settings/pricing/oci",
  "/settings/security",
  "/settings/sessions",
  "/settings/usage-costs",
  "/settings/users",
].sort();

test("final route inventory matches every Next.js page route", () => {
  const actualRoutes = collectPageRoutes(path.join(FRONTEND_ROOT, "app")).sort();
  assert.deepEqual(actualRoutes, expectedRoutes);
});

test("legacy route aliases remain compatibility redirects instead of duplicate UI", () => {
  assert.match(readFrontend("app/finops/ledger/page.tsx"), /redirect\("\/flow"\)/);
  assert.match(readFrontend("app/security/page.tsx"), /redirect\("\/settings\/security"\)/);
  assert.match(readFrontend("app/settings/page.tsx"), /redirect\("\/settings\/security"\)/);
});

test("canonical visualization documentation replaces the proven duplicate root copy", () => {
  assert.equal(fs.existsSync(path.join(REPO_ROOT, "AVEN_DATA_VISUALIZATION_SYSTEM.md")), false);
  assert.equal(fs.existsSync(path.join(REPO_ROOT, "docs/brand/aven/AVEN_DATA_VISUALIZATION_SYSTEM.md")), true);
  assert.match(readRepo("docs/brand/aven/README.md"), /AVEN_DATA_VISUALIZATION_SYSTEM\.md/);
});

test("final hardcode gate covers migrated route families and active compatibility styling", () => {
  const source = readFrontend("scripts/check-design-system.mjs");
  assert.match(source, /path\.join\(ROOT, "app", "legacy-theme-compat\.css"\)/);
  assert.match(source, /path\.join\(ROOT, "app", "opportunities"\)/);
  assert.match(source, /path\.join\(ROOT, "app", "settings"\)/);
  assert.match(source, /letter-spacing\\s\*:/);
  assert.doesNotMatch(source, /path\.join\(ROOT, "app", "opportunities", "page\.tsx"\)/);
  assert.doesNotMatch(source, /path\.join\(ROOT, "app", "settings", "appearance", "page\.tsx"\)/);
});

test("obsolete global shell overrides stay removed after the CSS-module shell migration", () => {
  const legacy = readFrontend("app/legacy-theme-compat.css");

  assert.doesNotMatch(legacy, /\.sidebar \.brand-label/);
  assert.doesNotMatch(legacy, /\.sidebar \.nav-label/);
  assert.doesNotMatch(legacy, /\.sidebar \.product-tag/);
  assert.doesNotMatch(legacy, /\.sidebar \.sidebar-tooltip/);
  assert.doesNotMatch(legacy, /\.main-nav/);
  assert.doesNotMatch(legacy, /!important/);
  assert.match(legacy, /letter-spacing:\s*var\(--type-heading-xl-letter-spacing\)/);
});

test("obsolete Task 23.25 layout patch stays removed after Dashboard and Opportunities migration", () => {
  const layout = readFrontend("app/layout.tsx");
  assert.equal(fs.existsSync(path.join(FRONTEND_ROOT, "app/task-23-25-layout.css")), false);
  assert.doesNotMatch(layout, /task-23-25-layout\.css/);
});

test("theme switching is presentation-only and cannot trigger domain requests or remount children", () => {
  const provider = readFrontend("components/theme-provider.tsx");
  assert.doesNotMatch(provider, /@\/lib\/api/);
  assert.doesNotMatch(provider, /@\/lib\/server-state/);
  assert.doesNotMatch(provider, /\bfetch\s*\(/);
  assert.doesNotMatch(provider, /useRouter|router\./);
  assert.match(provider, /persistThemePreference\(getBrowserStorage\(\), preference\)/);
  assert.match(provider, /applyTheme\(preference\)/);
  assert.match(provider, /<ThemeContext\.Provider value=\{value\}>\{children\}<\/ThemeContext\.Provider>/);
});

test("active compatibility layers are preserved and final QA documentation is registered", () => {
  const layout = readFrontend("app/layout.tsx");
  const tokenIndex = readFrontend("app/styles/tokens/index.css");
  const readme = readRepo("docs/brand/aven/README.md");
  const qa = readRepo("docs/brand/aven/AVEN_VISUAL_QA_AND_LEGACY_CLEANUP.md");

  assert.match(layout, /import "\.\/legacy-theme-compat\.css"/);
  assert.match(tokenIndex, /@import "\.\/legacy\.css"/);
  assert.match(readme, /AVEN_VISUAL_QA_AND_LEGACY_CLEANUP\.md/);
  assert.match(qa, /## Preserved Compatibility Contracts/);
  assert.match(qa, /## Phase 24 Closure/);
});
