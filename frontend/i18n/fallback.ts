import type { AppLocale } from "./locales.mjs";

/** Avoid leaking raw keys or implementation errors to end users. */
export function unavailableTranslation(locale: AppLocale): string {
  return locale === "en-US" ? "Translation unavailable" : "Tradução indisponível";
}
