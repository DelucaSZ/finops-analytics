import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(ROOT, "..");
const read = (relative) => fs.readFileSync(path.join(REPO, relative), "utf8");

test("Aven public product identity has a single frontend source of truth", () => {
  const brand = read("frontend/lib/brand.ts");
  assert.match(brand, /PRODUCT_NAME = "Aven"/);
  assert.match(brand, /PRODUCT_TAGLINE = "Clarity\. Flow\. Control\."/);
  assert.match(brand, /wordmarkFallback/);
  assert.match(brand, /symbolGradient/);
});

test("global metadata and authentication surfaces contain no visible legacy branding", () => {
  for (const file of [
    "frontend/app/layout.tsx",
    "frontend/app/login/page.tsx",
    "frontend/components/access-form.tsx",
    "frontend/app/mfa-setup/page.tsx",
    "frontend/app/settings/appearance/page.tsx",
    "backend/app/services/mailer.py",
  ]) {
    assert.doesNotMatch(read(file), /DeepOps|Deep Ops|NuvemIQ|Nuvem IQ/);
  }
  assert.match(read("backend/app/main.py"), /title="Aven API"/);
});

test("technical compatibility identifiers remain explicit and unchanged", () => {
  const preferences = read("frontend/lib/ui-preferences.mjs");
  const api = read("frontend/lib/api.ts");
  const shell = read("frontend/components/app-shell.tsx");
  const backend = read("backend/app/main.py");
  assert.match(preferences, /deepops\.theme/);
  assert.match(preferences, /deepops\.sidebar\.collapsed/);
  assert.match(api, /X-DeepOps-Request/);
  assert.match(api, /deepops:session-invalidated/);
  assert.match(shell, /nuvemiq_token/);
  assert.match(backend, /\/api\/v1\/deepops-costs/);
  assert.match(backend, /nuvemiq-api/);
});

test("technical rebrand documentation records raster and next-task readiness", () => {
  const docs = read("docs/brand/aven/AVEN_TECHNICAL_REBRAND.md");
  assert.match(docs, /Technical rebrand: COMPLETE/);
  assert.match(docs, /Raster-dependent runtime branding: PARTIAL/);
  assert.match(docs, /Is Task 24\.9 ready to start\? \*\*YES\*\*/);
});
