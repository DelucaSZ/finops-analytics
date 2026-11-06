import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createTranslator } from "next-intl";
import {
  DEFAULT_LOCALE,
  getLocaleCookieOptions,
  isSupportedLocale,
  LOCALE_COOKIE_NAME,
  normalizeLocale,
  readLocaleFromCookieHeader,
  resolveLocale,
  SUPPORTED_LOCALES,
} from "../i18n/locales.mjs";
import { parseUniqueJson, validateCatalogFiles, validateCatalogObjects } from "../scripts/check-i18n.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => readFileSync(path.join(ROOT, p), "utf8");
const catalog = (locale) => JSON.parse(read("i18n/messages/" + locale + ".json"));

test("official locales, fallback, and explicit preference priority", () => {
  assert.deepEqual(SUPPORTED_LOCALES, ["pt-BR", "en-US"]);
  assert.equal(DEFAULT_LOCALE, "pt-BR");
  for (const locale of SUPPORTED_LOCALES) assert.equal(isSupportedLocale(locale), true);
  for (const value of [null, undefined, "", "fr-FR", "es-ES", "en", {}, 1]) {
    assert.equal(isSupportedLocale(value), false);
    assert.equal(normalizeLocale(value), "pt-BR");
  }
  assert.equal(resolveLocale({ explicit: "en-US", persisted: "pt-BR" }), "en-US");
  assert.equal(resolveLocale({ explicit: "fr-FR", persisted: "en-US" }), "en-US");
  assert.equal(resolveLocale({ explicit: "fr-FR", persisted: "es-ES" }), "pt-BR");
});

test("cookie parser rejects corruption, accepts only allowlisted values", () => {
  assert.equal(LOCALE_COOKIE_NAME, "aven.locale");
  assert.equal(readLocaleFromCookieHeader("session=s; aven.locale=en-US; other=x"), "en-US");
  assert.equal(readLocaleFromCookieHeader("aven.locale=pt-BR"), "pt-BR");
  assert.equal(readLocaleFromCookieHeader("aven.locale=fr-FR"), "pt-BR");
  assert.equal(readLocaleFromCookieHeader("aven.locale=%FF"), "pt-BR");
  assert.equal(readLocaleFromCookieHeader("aven.locale=%E0%A4%A"), "pt-BR");
  assert.equal(readLocaleFromCookieHeader(undefined), "pt-BR");
  assert.equal(readLocaleFromCookieHeader("theme=dark"), "pt-BR");
});

test("cookie persistence options are durable, HttpOnly and isolated from theme", () => {
  assert.deepEqual(getLocaleCookieOptions(false), {
    path: "/", sameSite: "lax", secure: false, httpOnly: true, maxAge: 31536000,
  });
  assert.equal(getLocaleCookieOptions(true).secure, true);
  assert.notEqual(LOCALE_COOKIE_NAME, "aven.theme");
  assert.doesNotMatch(read("i18n/actions.ts"), /localStorage|theme|sidebar/i);
});

test("catalog parity and valid ICU arguments are enforced", () => {
  const result = validateCatalogFiles();
  assert.ok(result.keys >= 6);
  assert.ok(result.namespaces >= 2);
  const pt = catalog("pt-BR");
  const en = catalog("en-US");
  assert.throws(() => validateCatalogObjects(pt, { ...en, common: {} }), /parity mismatch/i);
  assert.throws(() => validateCatalogObjects(
    { common: { value: "{count} results" } },
    { common: { value: "{total} results" } },
  ), /parameter mismatch/i);
  assert.throws(() => validateCatalogObjects(
    { common: { value: "{count, plural, one {one}}" } },
    { common: { value: "{count, plural, one {one}}" } },
  ), /Invalid ICU|Missing ICU other case/);
  assert.throws(() => parseUniqueJson('{"common":{"save":"Save","save":"Again"}}'), /Duplicate translation key: common.save/);
  assert.throws(() => parseUniqueJson('{"bad":}'), /JSON|Expected/);
});

test("next-intl resolves real translated strings, interpolation and ICU plural rules", () => {
  for (const [locale, expected] of [
    ["pt-BR", ["Salvar", "Nenhum resultado", "1 resultado", "3 resultados"]],
    ["en-US", ["Save", "No results", "1 result", "3 results"]],
  ]) {
    const t = createTranslator({ locale, messages: catalog(locale), namespace: "common" });
    assert.equal(t("actions.save"), expected[0]);
    assert.equal(t("results.count", { count: 0 }), expected[1]);
    assert.equal(t("results.count", { count: 1 }), expected[2]);
    assert.equal(t("results.count", { count: 3 }), expected[3]);
  }
});

test("request-specific server config, html lang and SSR snapshot preserve the App Router", () => {
  const root = read("app/layout.tsx");
  const config = read("i18n/request.ts");
  const server = read("i18n/server.ts");
  const provider = read("components/locale-provider.tsx");
  const hook = read("i18n/use-locale-preference.ts");
  const action = read("i18n/actions.ts");
  assert.match(config, /getRequestConfig/);
  assert.match(server, /await cookies\(\)/);
  assert.match(root, /const locale = await getLocale\(\)/);
  assert.match(root, /const messages = await getMessages\(\)/);
  assert.match(root, /lang=\{locale\}/);
  assert.match(root, /<LocaleProvider locale=\{locale\} messages=\{messages\}>/);
  assert.match(provider, /<NextIntlClientProvider/);
  assert.match(root, /<ThemeProvider>/);
  assert.match(hook, /router\.refresh\(\)/);
  assert.match(action, /cookieStore\.set\(LOCALE_COOKIE_NAME/);
  assert.doesNotMatch(root + config + hook, /localePrefix|\/\[locale\]/);
  assert.doesNotMatch(hook + action, /localStorage/);
});
