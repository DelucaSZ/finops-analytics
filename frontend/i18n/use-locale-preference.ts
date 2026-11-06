"use client";

import { useCallback, useRef, useState, useTransition } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { updateLocalePreference } from "./actions";
import { isSupportedLocale } from "./locales.mjs";

/** The official HttpOnly cookie remains the source of truth, including on SSR. */
export function useLocalePreference() {
  const locale = useLocale();
  const router = useRouter();
  const [isRefreshing, startTransition] = useTransition();
  const [isSaving, setIsSaving] = useState(false);
  const inFlight = useRef(false);

  const changeLocale = useCallback(async (requested: string): Promise<boolean> => {
    if (!isSupportedLocale(requested) || inFlight.current) return false;
    if (requested === locale) return true;
    inFlight.current = true;
    setIsSaving(true);
    try {
      const result = await updateLocalePreference(requested);
      if (!result.ok) return false;
      startTransition(() => router.refresh());
      return true;
    } catch {
      return false;
    } finally {
      inFlight.current = false;
      setIsSaving(false);
    }
  }, [locale, router]);

  return { locale, changeLocale, isPending: isSaving || isRefreshing };
}
