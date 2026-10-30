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
const BRAND = path.join(ROOT, "components", "brand", "brand-logo.tsx");
const BRAND_LIB = path.join(ROOT, "lib", "brand.ts");
const COMPONENT_TOKENS = path.join(ROOT, "app", "styles", "tokens", "components.css");
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
  assert.match(source, /<AvenLogo[\s\S]*variant="vertical"[\s\S]*surface=\{surface\}[\s\S]*priority/);
  assert.match(source, /className=\{styles\.brandHero\}/);
  assert.doesNotMatch(source, /FINOPS MULTI-CLOUD/);
  assert.doesNotMatch(source, /Complexidade por baixo\. Clareza por cima\./);
  assert.doesNotMatch(source, /brandCopy|PRODUCT_TAGLINE|brandLogoSurface/);
});

test("auth branding consumes the Full HD Aven assets through the centralized surface-aware component", () => {
  const brand = fs.readFileSync(BRAND, "utf8");
  const brandLib = fs.readFileSync(BRAND_LIB, "utf8");
  const styles = authStyles();
  const tokens = fs.readFileSync(COMPONENT_TOKENS, "utf8");

  assert.match(brand, /export function AvenLogo/);
  assert.match(brand, /logoSource\(resolvedVariant, resolvedSurface\)/);
  assert.match(brandLib, /aven_logo_horizontal_no_tagline_light_ui_4096\.png/);
  assert.match(brandLib, /aven_logo_horizontal_no_tagline_dark_ui_4096\.png/);
  assert.match(brandLib, /aven_logo_vertical_light_ui_4096\.png/);
  assert.match(brandLib, /aven_logo_vertical_dark_ui_4096\.png/);
  assert.match(tokens, /--auth-brand-hero-inline-size:/);
  assert.match(tokens, /--auth-brand-hero-medium-inline-size:/);
  assert.match(tokens, /--auth-form-max-inline-size:/);
  assert.match(styles, /\.brandLogo[\s\S]*var\(--auth-brand-hero-inline-size\)/);
  assert.match(styles, /\.brandLogo img[\s\S]*inline-size: 100%/);
  assert.doesNotMatch(styles, /background:\s*var\(--aven-color-neutral-0\)/);
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
  assert.doesNotMatch(settings, /security-card|mfa-card|form-error|className="button|security-actions|mfa-saved/);
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

test("login follows the semantic Aven canvas across Light, Dark and System with responsive auth composition", () => {
  const styles = authStyles();
  assert.match(styles, /background:\s*var\(--application-background\)/);
  assert.doesNotMatch(styles, /gradient-background-light|gradient-background-dark/);
  assert.doesNotMatch(styles, /html\[data-theme="dark"\]/);
  assert.doesNotMatch(styles, /justify-content:\s*space-between/);
  assert.match(styles, /\.brandPanel[\s\S]*justify-content: center/);
  assert.match(styles, /\.brandHero[\s\S]*justify-items: center/);
  assert.match(styles, /@media \(max-width: 60rem\)[\s\S]*--auth-brand-hero-medium-inline-size/);
  assert.match(styles, /@media \(max-width: 42rem\)[\s\S]*\.brandPanel[\s\S]*display: none/);
  assert.match(styles, /min-block-size: 100dvh/);
  assert.match(styles, /-webkit-autofill/);
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
