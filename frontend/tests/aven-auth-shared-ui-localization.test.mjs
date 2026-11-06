import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createTranslator } from "next-intl";
import { validateCatalogFiles } from "../scripts/check-i18n.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (name) => readFileSync(path.join(ROOT, name), "utf8");
const catalog = (locale) => JSON.parse(read("i18n/messages/" + locale + ".json"));
const login = read("app/login/page.tsx");
const access = read("components/access-form.tsx");
const mfa = read("components/mfa-settings.tsx");
const setup = read("app/mfa-setup/page.tsx");
const identity = read("components/identity-proof.tsx");

test("25.4 catalogs have equivalent keys, valid ICU and bilingual authentication copy", () => {
  const result = validateCatalogFiles();
  assert.ok(result.keys >= 160);
  for (const [locale, title, signIn, remaining] of [
    ["pt-BR", "Bem-vindo de volta", "Entrar", "2 códigos de recuperação disponíveis."],
    ["en-US", "Welcome back", "Sign in", "2 recovery codes available."],
  ]) {
    const t = createTranslator({ locale, messages: catalog(locale), namespace: "auth" });
    assert.equal(t("login.title"), title);
    assert.equal(t("login.submit"), signIn);
    assert.equal(t("mfa.recoveryRemaining", { count: 2 }), remaining);
    assert.ok(t("mfa.setupPageTitle", { product: "Aven" }).includes("Aven"));
    assert.ok(t("access.passwordInstructions", { min: 12, max: 128 }).includes("128"));
    assert.ok(t("errors.invalidCredentials"));
    assert.ok(t("identity.success"));
  }
});

test("login, MFA and access flows use semantic translation keys, not stored translated errors", () => {
  assert.match(login, /useTranslations\("auth"\)/);
  assert.match(login, /setError\(authErrorKey\(err, challenge \? "verify" : "login"\)\)/);
  assert.match(login, /t\("login.submitting"\)/);
  assert.match(login, /t\("mfa.recoveryInstruction"\)/);
  assert.match(access, /useTranslations\("auth"\)/);
  assert.match(access, /setMessage\(true\)/);
  assert.ok(access.includes("t(`access.${mode}.success`)"));
  assert.match(access, /window\.location\.hash\.slice\(1\)/);
  assert.match(access, /window\.history\.replaceState\(null, "", window\.location\.pathname\)/);
  assert.match(mfa, /t\("recoveryRemaining", \{ count: status\.recovery_codes_remaining \}\)/);
  assert.match(mfa, /setError\(authErrorKey\(err, "configure"\)\)/);
  assert.match(setup, /t\("mfa.setupPageTitle"/);
  assert.match(identity, /t\("success"\)/);
  for (const source of [login, access, mfa, setup, identity]) {
    assert.doesNotMatch(source, /err\.message|result\.message|setError\("[À-ÿ]/);
  }
});

test("auth endpoint payloads and security-critical URL fragments are unchanged", () => {
  assert.match(login, /JSON\.stringify\(\{ email, password \}\)/);
  assert.match(login, /JSON\.stringify\(\{ challenge, code \}\)/);
  assert.match(login, /router\.replace\(result\.enrollment_required \? "\/mfa-setup" : "\/"\)/);
  for (const endpoint of ["/auth/forgot-password", "/auth/reset-password", "/auth/accept-invitation"]) {
    assert.ok(access.includes(endpoint));
  }
  assert.match(access, /token\.length !== 43/);
  assert.match(mfa, /setCodes\(result\.recovery_codes\)/);
  assert.match(mfa, /setSetup\(result\)/);
  const classifier = read("lib/auth-error.ts");
  assert.match(classifier, /error instanceof ApiError/);
  assert.doesNotMatch(classifier, /error\.message|error\.detail|console\.log/);
});

test("shared controls use localized defaults without overriding caller-owned labels", () => {
  const pagination = read("components/ui/pagination.tsx");
  const dialog = read("components/ui/dialog.tsx");
  const drawer = read("components/ui/drawer.tsx");
  const toast = read("components/ui/toast.tsx");
  const selectors = read("components/aven/selectors.tsx");
  const datePicker = read("components/aven/date-range-picker.tsx");
  const dataState = read("components/aven/data-state.tsx");
  const authLayout = read("components/auth/auth-layout.tsx");
  assert.match(pagination, /t\("page", \{ page: value \}\)/);
  assert.match(dialog, /t\("dialogClose"\)/);
  assert.match(drawer, /t\("drawerClose"\)/);
  assert.match(toast, /t\("dismiss"\)/);
  assert.match(selectors, /selectAllLabel \?\? t\("selectAll"\)/);
  assert.match(selectors, /props\.formatSelectionSummary \?\?/);
  assert.match(datePicker, /presetLabel \?\? t\("period"\)/);
  assert.match(dataState, /emptyTitle \?\? t\("noData"\)/);
  assert.match(authLayout, /t\("authPanel"\)/);
  for (const locale of ["pt-BR", "en-US"]) {
    const common = createTranslator({ locale, messages: catalog(locale), namespace: "common" });
    assert.equal(common("pagination.page", { page: 9 }), locale === "pt-BR" ? "Página 9" : "Page 9");
    assert.equal(common("selectors.accountCount", { count: 3 }),
      locale === "pt-BR" ? "3 contas selecionadas" : "3 accounts selected");
  }
});

test("technical identifiers and consumer-supplied shared content remain untouched", () => {
  const resource = read("components/aven/resource-identifier.tsx");
  const recommendation = read("components/aven/recommendation-card.tsx");
  const displays = read("components/aven/displays.tsx");
  assert.match(resource, /technicalId/);
  assert.match(resource, /copyLabel \?\? t\("copy"\)/);
  assert.match(recommendation, /t\("potentialSavings"\)/);
  assert.match(displays, /locale \?\? activeLocale/);
  assert.match(displays, /t\("announcement"/);
  assert.match(read("components/ui/empty-state.tsx"), /title: ReactNode/);
  assert.match(read("components/ui/alert.tsx"), /description\?: ReactNode/);
});
