export const THEME_STORAGE_KEY = "deepops.theme";
export const SIDEBAR_STORAGE_KEY = "deepops.sidebar.collapsed";
export const THEME_MEDIA_QUERY = "(prefers-color-scheme: dark)";

export const THEME_PREFERENCES = Object.freeze(["system", "light", "dark"]);

export function isThemePreference(value) {
  return THEME_PREFERENCES.includes(value);
}

export function normalizeThemePreference(value) {
  if (value === true) return "dark";
  if (value === false) return "light";

  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "true") return "dark";
  if (normalized === "false") return "light";
  return isThemePreference(normalized) ? normalized : "system";
}

export function resolveThemePreference(preference, systemPrefersDark = false) {
  const normalized = normalizeThemePreference(preference);
  if (normalized === "system") return systemPrefersDark ? "dark" : "light";
  return normalized;
}

export function readStoredThemePreference(storage) {
  let stored = null;
  try {
    stored = storage?.getItem(THEME_STORAGE_KEY) ?? null;
  } catch {
    return "system";
  }

  const preference = normalizeThemePreference(stored);

  // Normalize legacy boolean values and self-heal invalid persisted values.
  if (stored !== null && stored !== preference) {
    try {
      storage?.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // Theme resolution remains functional in memory when persistence is unavailable.
    }
  }

  return preference;
}

export function persistThemePreference(storage, preference) {
  const normalized = normalizeThemePreference(preference);
  try {
    storage?.setItem(THEME_STORAGE_KEY, normalized);
    return true;
  } catch {
    return false;
  }
}

export function getThemeBootstrapScript() {
  const storageKey = JSON.stringify(THEME_STORAGE_KEY);
  const mediaQuery = JSON.stringify(THEME_MEDIA_QUERY);
  const validPreferences = JSON.stringify(THEME_PREFERENCES);

  return `
(() => {
  const root = document.documentElement;
  const storageKey = ${storageKey};
  const validPreferences = ${validPreferences};
  let stored = null;
  let preference = "system";

  try {
    stored = window.localStorage.getItem(storageKey);
  } catch {}

  if (stored === "true") preference = "dark";
  else if (stored === "false") preference = "light";
  else if (validPreferences.includes(stored)) preference = stored;

  if (stored !== null && stored !== preference) {
    try { window.localStorage.setItem(storageKey, preference); } catch {}
  }

  const media = window.matchMedia ? window.matchMedia(${mediaQuery}) : null;
  const resolved = preference === "system" ? (media?.matches ? "dark" : "light") : preference;

  root.dataset.themePreference = preference;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
})();
`;
}

export function parseSidebarCollapsed(value) {
  return String(value || "").trim().toLowerCase() === "true";
}

export function serializeSidebarCollapsed(collapsed) {
  return collapsed ? "true" : "false";
}
