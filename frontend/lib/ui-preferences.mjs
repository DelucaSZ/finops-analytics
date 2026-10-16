export const THEME_STORAGE_KEY = "deepops.theme";
export const SIDEBAR_STORAGE_KEY = "deepops.sidebar.collapsed";

export const THEME_PREFERENCES = Object.freeze(["system", "light", "dark"]);

export function normalizeThemePreference(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return THEME_PREFERENCES.includes(normalized) ? normalized : "system";
}

export function resolveThemePreference(preference, systemPrefersDark = false) {
  const normalized = normalizeThemePreference(preference);
  if (normalized === "system") return systemPrefersDark ? "dark" : "light";
  return normalized;
}

export function parseSidebarCollapsed(value) {
  return String(value || "").trim().toLowerCase() === "true";
}

export function serializeSidebarCollapsed(collapsed) {
  return collapsed ? "true" : "false";
}
