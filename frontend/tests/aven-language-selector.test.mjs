import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { createTranslator } from "next-intl";
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from "../i18n/locales.mjs";
import { scanDirectory, summarize } from "../scripts/check-design-system.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (file) => readFileSync(path.join(ROOT, file), "utf8");
const catalogs = Object.fromEntries(SUPPORTED_LOCALES.map((locale) =>
  [locale, JSON.parse(read("i18n/messages/" + locale + ".json"))],
));

test("selector uses official locale preference and RSC refresh, never separate storage", () => {
  const selector = read("components/app-shell/language-control.tsx");
  const hook = read("i18n/use-locale-preference.ts");
  const root = read("app/layout.tsx");
  assert.match(selector, /useLocalePreference\(\)/);
  assert.match(selector, /changeLocale\(requested\)/);
  assert.match(selector, /disabled=\{isPending\}/);
  assert.match(selector, /role="menuitemradio"/);
  assert.match(selector, /aria-checked=\{selected\}/);
  assert.match(selector, /role="alert"/);
  assert.match(selector, /<Flag src=\{current\.flag\}/);
  assert.match(selector, /aria-label=\{t\("current"/);
  assert.match(hook, /updateLocalePreference\(requested\)/);
  assert.match(hook, /router\.refresh\(\)/);
  assert.match(hook, /inFlight\.current/);
  assert.match(root, /lang=\{locale\}/);
  assert.doesNotMatch(selector + hook, /localStorage|window\.location\.reload|document\.cookie/);
  assert.equal(DEFAULT_LOCALE, "pt-BR");
});

test("Topbar order and navigation localization preserve existing responsibilities", () => {
  const shell = read("components/app-shell/application-shell.tsx");
  const start = shell.indexOf('<div className={styles.topbarUtilities}>');
  const stop = shell.indexOf("</div>", start);
  const utilities = shell.slice(start, stop);
  assert.ok(utilities.indexOf("<ThemeControl />") < utilities.indexOf("<LanguageControl />"));
  assert.ok(utilities.indexOf("<LanguageControl />") < utilities.indexOf("<UserControl"));
  assert.match(shell, /useTranslations\("shell\.navigation"\)/);
  assert.match(shell, /label=\{tNavigation\(item\.labelKey\)\}/);
  assert.match(shell, /content=\{label\}/);
  assert.match(shell, /onClick=\{\(\) => void onLogout\(\)\}/);
});

test("routes and active matching remain stable while labels become keys", () => {
  const nav = read("components/app-shell/navigation.ts");
  assert.doesNotMatch(nav, /label:\s*"(?:Dashboard|Oportunidades|Inventory|Fluxo|Billing|Coletas|Configurações)"/);
  for (const key of ["dashboard","opportunities","inventory","flow","billing","reservations","collections","settings"]) {
    assert.match(nav, new RegExp('labelKey: "' + key + '"'));
    assert.ok(catalogs["pt-BR"].shell.navigation[key]);
    assert.ok(catalogs["en-US"].shell.navigation[key]);
  }
  for (const route of ["/opportunities","/inventory","/flow","/billing","/rds/reservations","/collections","/settings"]) {
    assert.ok(nav.includes('href: "' + route + '"'));
  }
  assert.match(nav, /pathname === item\.href/);
  assert.match(nav, /activePrefixes\?\.some/);
});

test("both catalogs render navigation, theme, language, session, a11y and user menu", () => {
  for (const locale of SUPPORTED_LOCALES) {
    const t = createTranslator({locale,messages:catalogs[locale],namespace:"shell"});
    for (const key of [
      "navigation.dashboard","navigation.settings","sidebar.open","sidebar.collapse",
      "sidebar.mainNavigation","sidebar.mobileNavigation","theme.light","theme.dark",
      "theme.system","theme.select","user.signOut","user.signingOut",
      "user.authenticatedAccount","accessibility.skipToContent","session.verificationFailed",
      "language.select","language.changeFailed"
    ]) assert.ok(t(key));
    assert.ok(t("theme.current",{theme:t("theme.light")}));
    assert.ok(t("language.current",{language:t("language.englishUnitedStates")}));
    assert.ok(t("theme.optionSelected",{option:t("theme.light")}));
    assert.equal(t("language.portugueseBrazil"),"Português (Brasil)");
    assert.equal(t("language.englishUnitedStates"),"English (US)");
  }
  assert.equal(catalogs["pt-BR"].shell.navigation.dashboard,"Visão geral");
  assert.equal(catalogs["en-US"].shell.navigation.dashboard,"Overview");
  assert.equal(catalogs["en-US"].shell.theme.system,"System");
});

test("flags are local, selected flag remains visible in responsive shell", () => {
  const selector=read("components/app-shell/language-control.tsx");
  const css=read("components/app-shell/app-shell.module.css");
  assert.match(selector, /flag: "\/flags\/br\.svg"/);
  assert.match(selector, /flag: "\/flags\/us\.svg"/);
  assert.match(selector, /width=\{32\} height=\{24\}/);
  assert.match(css, /\.languageFlag\s*\{/);
  assert.match(css, /\.topbarControlLabel[\s\S]*display: none/);
  assert.match(read("public/flags/br.svg"), /<svg/);
  assert.match(read("public/flags/us.svg"), /<svg/);
});

test("keyboard menu accepts radio items and Aven shell stays tokenized", () => {
  const primitive=read("components/ui/dropdown.tsx");
  assert.match(primitive, /menuitemradio/);
  assert.match(primitive, /ArrowDown/);
  assert.match(primitive, /ArrowUp/);
  assert.match(primitive, /Escape/);
  const violations = [
    ...scanDirectory(path.join(ROOT,"components/app-shell")),
    ...scanDirectory(path.join(ROOT,"components/ui/dropdown.tsx")),
  ];
  assert.deepEqual(summarize(violations),{colors:0,spacing:0,radius:0,typography:0});
});
