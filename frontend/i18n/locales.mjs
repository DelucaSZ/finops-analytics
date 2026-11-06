export const SUPPORTED_LOCALES = Object.freeze(["pt-BR", "en-US"]);
export const DEFAULT_LOCALE = "pt-BR";
export const LOCALE_COOKIE_NAME = "aven.locale";
export const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export function isSupportedLocale(value) {
  return typeof value === "string" && SUPPORTED_LOCALES.includes(value);
}

export function normalizeLocale(value) {
  return isSupportedLocale(value) ? value : DEFAULT_LOCALE;
}

export function resolveLocale({ explicit, persisted } = {}) {
  if (isSupportedLocale(explicit)) return explicit;
  return normalizeLocale(persisted);
}

export function readLocaleFromCookieHeader(header) {
  if (typeof header !== "string") return DEFAULT_LOCALE;
  for (const entry of header.split(";")) {
    const index = entry.indexOf("=");
    if (index < 0 || entry.slice(0, index).trim() !== LOCALE_COOKIE_NAME) continue;
    try {
      const rawValue = entry.slice(index + 1).trim().replace(/^"|"$/g, "");
      return normalizeLocale(decodeURIComponent(rawValue));
    } catch {
      return DEFAULT_LOCALE;
    }
  }
  return DEFAULT_LOCALE;
}

export function getLocaleCookieOptions(isProduction = false) {
  return {
    path: "/",
    sameSite: "lax",
    secure: isProduction === true,
    httpOnly: true,
    maxAge: LOCALE_COOKIE_MAX_AGE,
  };
}
