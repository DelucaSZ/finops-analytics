import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createTranslator } from "next-intl";
import { scanFileCandidates, newCandidates } from "../scripts/check-i18n-coverage.mjs";
import { scanTranslationReferences, checkTranslationReferences } from "../scripts/check-i18n-references.mjs";
import { validateCatalogFiles } from "../scripts/check-i18n.mjs";
import {
  DEFAULT_LOCALE, LOCALE_COOKIE_NAME, normalizeLocale, readLocaleFromCookieHeader,
} from "../i18n/locales.mjs";
import {
  formatLocaleCurrency, formatLocalePercentage, formatLocaleDate, formatLocaleDateTime,
} from "../i18n/formatters.mjs";
import { formatNu } from "../lib/rds-reservations-query.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = file => readFileSync(path.join(ROOT, file), "utf8");
const messages = locale => JSON.parse(source("i18n/messages/" + locale + ".json"));

test("catalogs have exact structural and ICU parity, including corrected HTTPS copy", () => {
  const result = validateCatalogFiles();
  assert.ok(result.keys > 2100);
  for (const locale of ["pt-BR", "en-US"]) {
    const t = createTranslator({ locale, messages: messages(locale), namespace: "settings.https" });
    assert.ok(t("endpointVerified").length > 5);
    assert.ok(t("automaticExplanation").includes("Caddy"));
    assert.ok(t("validatedCertificate", { issuer: "CA", date: "2026-11-10" }).includes("CA"));
    assert.equal(t("endpointCount", { count: 1 }).includes("1"), true);
  }
  assert.equal(createTranslator({locale:"en-US", messages: messages("en-US"), namespace: "settings.https"})("endpointCount", {count: 2}), "2 endpoints");
  assert.equal(createTranslator({locale:"pt-BR", messages: messages("pt-BR"), namespace: "settings.https"})("endpointCount", {count: 2}), "2 endpoints");
});

test("source candidate scanner recognizes user copy without treating codes as labels", () => {
  const fixture = [
    'export function Sample() {',
    ' const options = [{value: "AWS", label: "Cloud account"}];',
    ' return <section aria-label="Example report">',
    '   <p>Sem dados disponíveis</p>',
    '   <button title="Try again">Salvar</button>',
    '   <code>ARN</code><div data-code="VERIFIED" />',
    ' </section>;',
    '}',
  ].join("\n");
  const candidates = scanFileCandidates(fixture, "frontend/app/example/page.tsx");
  const texts = candidates.map(item => item.text);
  for (const text of ["Cloud account", "Example report", "Sem dados disponíveis", "Try again", "Salvar"]) {
    assert.ok(texts.includes(text), "Missing candidate: " + text);
  }
  assert.ok(!texts.includes("ARN"));
  assert.ok(!texts.includes("VERIFIED"));
  const after = scanFileCandidates(fixture.replace(">Salvar</button>", ">{t('save')}</button>"),
    "frontend/app/example/page.tsx");
  assert.ok(!newCandidates(after, candidates).some(item => item.text === "Salvar"));
  assert.equal(newCandidates(candidates, after).filter(item => item.text === "Salvar").length, 1);
});

test("static references are checked with namespace scopes; dynamic keys require review", () => {
  const fixture = [
    'function A() { const t = useTranslations("common"); t("actions.save"); t(key); }',
    'async function B() { const tr = await getTranslations({namespace:"settings.https"}); tr("domain"); }',
    'function C() { const t = useTranslations("shell"); t.rich("something"); }',
  ].join("\n");
  const refs = scanTranslationReferences(fixture);
  assert.deepEqual(refs.resolved.map(item => item.key),
    ["common.actions.save", "settings.https.domain", "shell.something"]);
  assert.equal(refs.dynamic.length, 1);
  const audited = checkTranslationReferences([["fixture.tsx",fixture]], {"pt-BR":messages("pt-BR")});
  assert.ok(audited.missing.some(item => item.key === "shell.something"));
  assert.ok(!audited.missing.some(item => item.key === "common.actions.save"));
});

test("locale preference is isolated from theme, sessions and unsupported cookies", () => {
  assert.equal(DEFAULT_LOCALE, "pt-BR");
  assert.equal(LOCALE_COOKIE_NAME, "aven.locale");
  for (const invalid of ["invalid", "", "en", null, undefined]) {
    assert.equal(normalizeLocale(invalid), "pt-BR");
  }
  assert.equal(readLocaleFromCookieHeader("session=one; aven.locale=en-US; theme=dark"), "en-US");
  assert.equal(readLocaleFromCookieHeader("session=one; aven.locale=%E0%A4%A"), "pt-BR");
  assert.match(source("i18n/actions.ts"), /isSupportedLocale\(requested\)/);
  assert.match(source("i18n/use-locale-preference.ts"), /router\.refresh\(\)/);
  assert.match(source("app/layout.tsx"), /lang=\{locale\}/);
});

test("both locales format money, percentages, civil dates and NU without changing inputs", () => {
  const amount = "1234.56", date = "2024-02-29", nu = 1234.5;
  const ptMoney = formatLocaleCurrency(amount, "USD", "pt-BR").replace(/\u00a0/g, " ");
  const enMoney = formatLocaleCurrency(amount, "USD", "en-US").replace(/\u00a0/g, " ");
  assert.match(ptMoney, /1\.234,56/);
  assert.match(enMoney, /1,234\.56/);
  assert.equal(formatLocalePercentage(12.5, "en-US"), "12.5%");
  assert.equal(formatLocalePercentage(.125, "en-US", {valueMode:"fraction"}), "12.5%");
  assert.equal(formatLocaleDate(date, "pt-BR"), "29/02/2024");
  assert.equal(formatLocaleDate(date, "en-US"), "02/29/2024");
  assert.equal(formatLocaleDate("2026-02-29", "en-US"), "—");
  assert.equal(formatNu(nu, "pt-BR"), "1.234,5 NU");
  assert.equal(formatNu(nu, "en-US"), "1,234.5 NU");
  assert.equal(formatLocaleDateTime("2026-11-10T00:30:00Z", "en-US", {timeZone:"UTC"}).includes("11/10/26"), true);
  assert.deepEqual({amount,date,nu},{amount:"1234.56",date:"2024-02-29",nu:1234.5});
});

test("HTTPS diagnostics now translate frontend copy but preserve server diagnostics", () => {
  const page = source("app/settings/https/page.tsx");
  for (const key of ["endpointVerified", "endpointUnreachable", "trustNotEvaluated",
    "automaticExplanation", "chainHelp", "validatedCertificate"]) {
    assert.ok(page.includes('t("' + key + '")') ||
      (key === "validatedCertificate" && page.includes('t("validatedCertificate",')));
  }
  assert.match(page, /status\.endpoint_validation\.message/);
  assert.match(page, /status\.trust\.message/);
  assert.match(page, /endpoint\.message/);
  assert.doesNotMatch(page, /Domínio: <code>|DNS público:|Validação do endpoint:|No modo automático, o Caddy/);
  assert.match(page, /\/tls\/validate/);
  assert.match(page, /\/tls\/apply/);
  assert.match(page, /reauthentication_required/);
});

test("remaining settings/collection labels are localized", async () => {
 const pt = messages("pt-BR");
 const en = messages("en-US");
 for (const locale of [pt, en]) {
   for (const key of ["mfaCode", "recoveryReason", "searchPrompt", "statusLabel"]) assert.ok(locale.settings.users[key]);
   assert.ok(locale.collections.compare.perMonth);
   assert.ok(locale.collections.workspace.collectionRun);
   assert.ok(locale.collections.investigation.baseline);
 }
 const userPage = source("app/settings/users/page.tsx");
 for (const key of ["mfaCode", "recoveryReason", "searchPrompt", "statusLabel"]) assert.ok(userPage.includes('t("' + key + '")'));
});

test("shared API errors localize known statuses without mutating contracts", () => {
 const pt = messages("pt-BR").errors.api;
 const en = messages("en-US").errors.api;
 assert.deepEqual(Object.keys(pt).sort(), Object.keys(en).sort());
 assert.match(pt.forbidden,/permissão/);
 assert.match(en.forbidden,/permission/);
 const api = source("lib/api.ts");
 assert.ok(api.includes('document.documentElement.lang'));
 assert.ok(api.includes('apiErrorText("sessionExpired")'));
 assert.ok(api.includes('apiErrorText("reauthentication")'));
 assert.ok(api.includes('/auth/csrf'));
 assert.ok(api.includes('credentials: "include"'));
});

test("theme selector preserves preference identifiers and localizes visible option copy", () => {
 const selector=source("components/theme-selector.tsx");
 assert.ok(selector.includes('useTranslations("settings.appearance")'));
 for(const value of ["light","dark","system"]) assert.ok(selector.includes('value: "'+value+'"'));
 for(const locale of ["pt-BR","en-US"]){const m=messages(locale).settings.appearance;for(const key of ["system","light","dark","systemDescription","lightDescription","darkDescription"])assert.ok(m[key]);}
});
