import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import {
  getThemeBootstrapScript,
  normalizeThemePreference,
  persistThemePreference,
  readStoredThemePreference,
  resolveThemePreference,
  THEME_MEDIA_QUERY,
  THEME_STORAGE_KEY,
} from "../lib/ui-preferences.mjs";

function createStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    snapshot() {
      return Object.fromEntries(values);
    },
  };
}

function runBootstrap({ stored = null, systemDark = false, throwOnStorage = false } = {}) {
  const root = { dataset: {}, style: {} };
  const storage = {
    value: stored,
    getItem() {
      if (throwOnStorage) throw new Error("blocked");
      return this.value;
    },
    setItem(_key, value) {
      if (throwOnStorage) throw new Error("blocked");
      this.value = value;
    },
  };
  const context = {
    document: { documentElement: root },
    window: {
      localStorage: storage,
      matchMedia(query) {
        assert.equal(query, THEME_MEDIA_QUERY);
        return { matches: systemDark };
      },
    },
  };

  vm.runInNewContext(getThemeBootstrapScript(), context);
  return { root, storage };
}

test("resolver matrix keeps preference distinct from resolved theme", () => {
  const matrix = [
    ["light", false, "light"],
    ["light", true, "light"],
    ["dark", false, "dark"],
    ["dark", true, "dark"],
    ["system", false, "light"],
    ["system", true, "dark"],
  ];

  for (const [preference, systemDark, expected] of matrix) {
    assert.equal(resolveThemePreference(preference, systemDark), expected);
  }
});

test("missing and invalid preferences fall back to system", () => {
  assert.equal(normalizeThemePreference(null), "system");
  assert.equal(normalizeThemePreference("purple"), "system");
});

test("storage reads, migrates legacy booleans and persists explicit preferences", () => {
  const storage = createStorage({ [THEME_STORAGE_KEY]: "true" });
  assert.equal(readStoredThemePreference(storage), "dark");
  assert.equal(storage.snapshot()[THEME_STORAGE_KEY], "dark");

  assert.equal(persistThemePreference(storage, "system"), true);
  assert.equal(readStoredThemePreference(storage), "system");
});

test("storage failures do not break theme resolution", () => {
  const blockedStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("blocked"); },
  };
  assert.equal(readStoredThemePreference(blockedStorage), "system");
  assert.equal(persistThemePreference(blockedStorage, "dark"), false);
});

test("pre-hydration bootstrap gives explicit dark priority over a light OS", () => {
  const { root } = runBootstrap({ stored: "dark", systemDark: false });
  assert.equal(root.dataset.themePreference, "dark");
  assert.equal(root.dataset.theme, "dark");
  assert.equal(root.style.colorScheme, "dark");
});

test("pre-hydration bootstrap resolves system against the current OS", () => {
  const dark = runBootstrap({ stored: "system", systemDark: true });
  assert.equal(dark.root.dataset.themePreference, "system");
  assert.equal(dark.root.dataset.theme, "dark");

  const light = runBootstrap({ stored: null, systemDark: false });
  assert.equal(light.root.dataset.themePreference, "system");
  assert.equal(light.root.dataset.theme, "light");
});

test("bootstrap self-heals invalid persisted values and survives blocked storage", () => {
  const invalid = runBootstrap({ stored: "purple", systemDark: true });
  assert.equal(invalid.root.dataset.themePreference, "system");
  assert.equal(invalid.root.dataset.theme, "dark");
  assert.equal(invalid.storage.value, "system");

  const blocked = runBootstrap({ stored: "dark", systemDark: true, throwOnStorage: true });
  assert.equal(blocked.root.dataset.themePreference, "system");
  assert.equal(blocked.root.dataset.theme, "dark");
});

test("provider owns runtime listeners, cleanup and multi-tab synchronization", async () => {
  const provider = await readFile(new URL("../components/theme-provider.tsx", import.meta.url), "utf8");
  assert.ok(provider.includes('theme !== "system"'));
  assert.ok(provider.includes('media.addEventListener("change", handleSystemThemeChange)'));
  assert.ok(provider.includes('media.removeEventListener("change", handleSystemThemeChange)'));
  assert.ok(provider.includes('media.addListener(handleLegacySystemThemeChange)'));
  assert.ok(provider.includes('window.addEventListener("storage", handleStorage)'));
  assert.ok(provider.includes('window.removeEventListener("storage", handleStorage)'));
  assert.ok(provider.includes("resolvedTheme"));
});

test("Aven semantic tokens are selected only by the resolved data-theme contract", async () => {
  const light = await readFile(new URL("../app/styles/tokens/semantic-light.css", import.meta.url), "utf8");
  const dark = await readFile(new URL("../app/styles/tokens/semantic-dark.css", import.meta.url), "utf8");

  assert.ok(light.includes('html[data-theme="light"]'));
  assert.ok(dark.includes('html[data-theme="dark"]'));
  for (const token of ["--background-primary", "--surface-primary", "--text-primary", "--border-subtle"]) {
    assert.ok(light.includes(token), `light theme missing ${token}`);
    assert.ok(dark.includes(token), `dark theme missing ${token}`);
  }
});
