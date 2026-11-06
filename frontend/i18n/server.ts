import "server-only";
import { cookies } from "next/headers";
import { LOCALE_COOKIE_NAME, normalizeLocale, type AppLocale } from "./locales.mjs";

/** Resolve locale per request. Never cache this result across users. */
export async function resolveServerLocale(): Promise<AppLocale> {
  const cookieStore = await cookies();
  return normalizeLocale(cookieStore.get(LOCALE_COOKIE_NAME)?.value);
}
