"use server";

import { cookies } from "next/headers";
import {
  getLocaleCookieOptions,
  isSupportedLocale,
  LOCALE_COOKIE_NAME,
} from "./locales.mjs";

/**
 * The sole write path for the locale preference. Called by the 25.3 selector;
 * the next RSC render will read this cookie, without changing the URL.
 */
export async function updateLocalePreference(requested: string) {
  if (!isSupportedLocale(requested)) {
    return { ok: false as const };
  }

  const cookieStore = await cookies();
  cookieStore.set(LOCALE_COOKIE_NAME, requested, getLocaleCookieOptions(process.env.NODE_ENV === "production"));
  return { ok: true as const, locale: requested };
}
