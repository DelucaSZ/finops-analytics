import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ACCESS_FORM = path.join(ROOT, "components", "access-form.tsx");
const ACCESS_STYLES = path.join(ROOT, "components", "access-form.module.css");
const source = () => fs.readFileSync(ACCESS_FORM, "utf8");

test("recovery, reset and invitation flows share the Aven AuthLayout and primitives", () => {
  const content = source();
  assert.match(content, /<AuthLayout>/);
  assert.match(content, /<Card className=/);
  assert.match(content, /<Input/);
  assert.match(content, /<Button/);
  assert.match(content, /<Alert variant="success"/);
  assert.match(content, /<Alert variant="danger"/);
  assert.doesNotMatch(content, /access-page|login-card|login-brand|login-icon|form-success|form-error|button primary full|auth-link/);
});

test("access flows preserve endpoints, token scrubbing and password-manager semantics", () => {
  const content = source();
  for (const endpoint of ["/auth/forgot-password", "/auth/accept-invitation", "/auth/reset-password"]) {
    assert.match(content, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
  assert.match(content, /window\.location\.hash\.slice\(1\)/);
  assert.match(content, /window\.history\.replaceState\(null, "", window\.location\.pathname\)/);
  assert.match(content, /autoComplete="email"/);
  assert.match(content, /autoComplete="new-password"/);
  assert.match(content, /href="\/login"/);
});

test("shared Aven access flow has zero structural visual hardcodes", () => {
  const violations = [
    ...scanDirectory(ACCESS_FORM),
    ...scanDirectory(ACCESS_STYLES),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
});
