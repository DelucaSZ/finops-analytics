"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  normalizeThemePreference,
  persistThemePreference,
  readStoredThemePreference,
  resolveThemePreference,
  THEME_MEDIA_QUERY,
  THEME_STORAGE_KEY,
  type ResolvedTheme,
  type ThemePreference,
} from "@/lib/ui-preferences.mjs";

interface ThemeContextValue {
  theme: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setTheme(theme: ThemePreference): void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

function getBrowserStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function systemPrefersDark() {
  return Boolean(window.matchMedia?.(THEME_MEDIA_QUERY).matches);
}

function applyThemeToDocument(preference: ThemePreference, prefersDark = systemPrefersDark()) {
  const resolved = resolveThemePreference(preference, prefersDark);
  const root = document.documentElement;

  // data-theme is the single CSS/runtime source for the resolved Light/Dark mode.
  root.dataset.themePreference = preference;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;

  return resolved;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  // Deterministic SSR snapshots prevent hydration divergence. The pre-hydration
  // bootstrap already applies the correct DOM theme before the first paint.
  const [theme, setThemeState] = useState<ThemePreference>("system");
  const [resolvedTheme, setResolvedTheme] = useState<ResolvedTheme>("light");
  const [initialized, setInitialized] = useState(false);

  const applyTheme = useCallback((preference: ThemePreference, prefersDark?: boolean) => {
    const resolved = applyThemeToDocument(preference, prefersDark);
    setResolvedTheme(resolved);
    return resolved;
  }, []);

  useEffect(() => {
    const preference = readStoredThemePreference(getBrowserStorage());
    setThemeState(preference);
    applyTheme(preference);
    setInitialized(true);
  }, [applyTheme]);

  const setTheme = useCallback((nextTheme: ThemePreference) => {
    const preference = normalizeThemePreference(nextTheme);
    setThemeState(preference);
    persistThemePreference(getBrowserStorage(), preference);
    applyTheme(preference);
  }, [applyTheme]);

  useEffect(() => {
    if (!initialized || theme !== "system" || !window.matchMedia) return;

    const media = window.matchMedia(THEME_MEDIA_QUERY);
    const handleSystemThemeChange = (event: MediaQueryListEvent) => {
      applyTheme("system", event.matches);
    };

    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", handleSystemThemeChange);
      return () => media.removeEventListener("change", handleSystemThemeChange);
    }

    // Safari/WebKit compatibility for older MediaQueryList implementations.
    const handleLegacySystemThemeChange = (event: MediaQueryListEvent) => {
      applyTheme("system", event.matches);
    };
    media.addListener(handleLegacySystemThemeChange);
    return () => media.removeListener(handleLegacySystemThemeChange);
  }, [applyTheme, initialized, theme]);

  useEffect(() => {
    if (!initialized) return;

    const handleStorage = (event: StorageEvent) => {
      if (event.key !== THEME_STORAGE_KEY) return;
      const preference = normalizeThemePreference(event.newValue);
      setThemeState(preference);
      applyTheme(preference);
    };

    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, [applyTheme, initialized]);

  const value = useMemo<ThemeContextValue>(() => ({
    theme,
    resolvedTheme,
    setTheme,
  }), [resolvedTheme, setTheme, theme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used within ThemeProvider");
  return context;
}
