export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY: "deepops.theme";
export const SIDEBAR_STORAGE_KEY: "deepops.sidebar.collapsed";
export const THEME_PREFERENCES: readonly ThemePreference[];

export function normalizeThemePreference(value: unknown): ThemePreference;
export function resolveThemePreference(
  preference: unknown,
  systemPrefersDark?: boolean,
): ResolvedTheme;
export function parseSidebarCollapsed(value: unknown): boolean;
export function serializeSidebarCollapsed(collapsed: boolean): "true" | "false";
