import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const LOGIN = path.join(ROOT, "app", "login");
const MFA_SETUP = path.join(ROOT, "app", "mfa-setup");
const AUTH = path.join(ROOT, "components", "auth");
const MFA_SETTINGS = path.join(ROOT, "components", "mfa-settings.tsx");
const MFA_SETTINGS_STYLES = path.join(ROOT, "components", "mfa-settings.module.css");
const DOCS = path.resolve(ROOT, "..", "docs", "brand", "aven");
const loginSource = () => fs.readFileSync(path.join(LOGIN, "page.tsx"), "utf8");
const authSource = () => fs.readFileSync(path.join(AUTH, "auth-layout.tsx"), "utf8");
const authStyles = () => fs.readFileSync(path.join(AUTH, "auth-layout.module.css"), "utf8");

test("Aven Login Experience exposes a reusable tokenized auth layout", () => {
  for (const file of ["auth-layout.tsx", "auth-layout.module.css"]) {
    assert.ok(fs.existsSync(path.join(AUTH, file)), `${file} should exist`);
  }
  const source = authSource();
  assert.match(source, /export function AuthLayout/);
  assert.match(source, /<BrandLogo variant="wordmark"/);
  assert.match(source, /PRODUCT_TAGLINE/);
  assert.match(source, /Complexidade por baixo\. Clareza por cima\./);
});

test("login composes official Aven primitives instead of legacy visual controls", () => {
  const source = loginSource();
  assert.match(source, /<AuthLayout>/);
  assert.match(source, /<Card className=/);
  assert.match(source, /<Input/);
  assert.match(source, /<Button/);
  assert.match(source, /<IconButton/);
  assert.match(source, /<Alert variant="danger"/);
  assert.doesNotMatch(source, /login-page|login-visual|login-card|button primary full|auth-link|form-error/);
});

test("login preserves the existing authentication, MFA and redirect contracts", () => {
  const source = loginSource();
  assert.match(source, /api\("\/auth\/mfa\/verify"/);
  assert.match(source, /\}>\("\/auth\/login"/);
  assert.match(source, /JSON\.stringify\(\{ email, password \}\)/);
  assert.match(source, /JSON\.stringify\(\{ challenge, code \}\)/);
  assert.match(source, /router\.replace\("\/"\)/);
  assert.match(source, /router\.replace\(result\.enrollment_required \? "\/mfa-setup" : "\/"\)/);
  assert.match(source, /href="\/forgot-password"/);
});

test("login keeps native form semantics, password-manager metadata and keyboard submit", () => {
  const source = loginSource();
  assert.match(source, /<form[^>]*onSubmit=\{submit\}/);
  assert.match(source, /type="email"/);
  assert.match(source, /autoComplete="username"/);
  assert.match(source, /autoComplete="current-password"/);
  assert.match(source, /autoComplete="one-time-code"/);
  assert.match(source, /type="submit"/);
  assert.match(source, /required/);
});

test("password visibility is accessible and MFA recovery remains available", () => {
  const source = loginSource();
  assert.match(source, /showPassword \? "Ocultar senha" : "Mostrar senha"/);
  assert.match(source, /<EyeOff/);
  assert.match(source, /<Eye/);
  assert.match(source, /Usar código de recuperação/);
  assert.match(source, /Usar autenticador/);
  assert.match(source, /Voltar ao login/);
});

test("MFA enrollment uses the same Aven auth shell and official primitives", () => {
  const page = fs.readFileSync(path.join(MFA_SETUP, "page.tsx"), "utf8");
  const settings = fs.readFileSync(MFA_SETTINGS, "utf8");
  assert.match(page, /<AuthLayout>/);
  assert.match(page, /<MfaSettings enrollment/);
  assert.match(page, /<Alert variant="danger"/);
  assert.match(page, /<Button/);
  assert.match(settings, /<Card className=/);
  assert.match(settings, /<Input/);
  assert.match(settings, /<Checkbox/);
  assert.match(settings, /<Spinner label=/);
  assert.match(settings, /<Alert/);
  assert.doesNotMatch(page, /mfa-enrollment|form-error|className="button/);
  assert.doesNotMatch(settings, /security-card|mfa-card|form-error|className="button|security-actions|recovery-codes|mfa-saved/);
});

test("MFA enrollment preserves existing API and redirect behavior", () => {
  const page = fs.readFileSync(path.join(MFA_SETUP, "page.tsx"), "utf8");
  const settings = fs.readFileSync(MFA_SETTINGS, "utf8");
  for (const endpoint of ["/auth/mfa/status", "/auth/mfa/setup", "/auth/mfa/confirm", "/auth/mfa/recovery-codes"]) {
    assert.match(settings, new RegExp(endpoint.replaceAll("/", "\\/")));
  }
  assert.match(page, /api\("\/auth\/logout", \{ method: "POST" \}\)/);
  assert.match(page, /router\.replace\("\/login"\)/);
  assert.match(settings, /router\.replace\("\/"\)/);
});

test("login uses the official Light and Dark institutional gradients and responsive auth composition", () => {
  const styles = authStyles();
  assert.match(styles, /background: var\(--gradient-background-light\)/);
  assert.match(styles, /html\[data-theme="dark"\][\s\S]*background: var\(--gradient-background-dark\)/);
  assert.match(styles, /@media \(max-width: 60rem\)/);
  assert.match(styles, /@media \(max-width: 42rem\)/);
  assert.match(styles, /min-block-size: 100dvh/);
});

test("hardcode gate is zero for all new and refactored Login and MFA sources", () => {
  const violations = [
    ...scanDirectory(AUTH),
    ...scanDirectory(LOGIN),
    ...scanDirectory(MFA_SETUP),
    ...scanDirectory(MFA_SETTINGS),
    ...scanDirectory(MFA_SETTINGS_STYLES),
  ];
  assert.deepEqual(summarize(violations), { colors: 0, spacing: 0, radius: 0, typography: 0 });
});

test("login documentation and Aven README integration exist", () => {
  assert.ok(fs.existsSync(path.join(DOCS, "AVEN_LOGIN_EXPERIENCE.md")));
  const readme = fs.readFileSync(path.join(DOCS, "README.md"), "utf8");
  assert.match(readme, /Aven Login Experience/);
});
