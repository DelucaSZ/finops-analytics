export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export interface ThemeStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const THEME_STORAGE_KEY: "deepops.theme";
export const SIDEBAR_STORAGE_KEY: "deepops.sidebar.collapsed";
export const THEME_MEDIA_QUERY: "(prefers-color-scheme: dark)";
export const THEME_PREFERENCES: readonly ThemePreference[];

export function isThemePreference(value: unknown): value is ThemePreference;
export function normalizeThemePreference(value: unknown): ThemePreference;
export function resolveThemePreference(
  preference: unknown,
  systemPrefersDark?: boolean,
): ResolvedTheme;
export function readStoredThemePreference(storage?: ThemeStorage | null): ThemePreference;
export function persistThemePreference(
  storage: ThemeStorage | null | undefined,
  preference: ThemePreference,
): boolean;
export function getThemeBootstrapScript(): string;
export function parseSidebarCollapsed(value: unknown): boolean;
export function serializeSidebarCollapsed(collapsed: boolean): "true" | "false";
