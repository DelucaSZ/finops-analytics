export type AppLocale = "pt-BR" | "en-US";
export const SUPPORTED_LOCALES: readonly AppLocale[];
export const DEFAULT_LOCALE: AppLocale;
export const LOCALE_COOKIE_NAME: "aven.locale";
export const LOCALE_COOKIE_MAX_AGE: number;
export function isSupportedLocale(value: unknown): value is AppLocale;
export function normalizeLocale(value: unknown): AppLocale;
export function resolveLocale(options?: { explicit?: unknown; persisted?: unknown }): AppLocale;
export function readLocaleFromCookieHeader(header: unknown): AppLocale;
export function getLocaleCookieOptions(isProduction?: boolean): {
  path: "/";
  sameSite: "lax";
  secure: boolean;
  httpOnly: true;
  maxAge: number;
};
