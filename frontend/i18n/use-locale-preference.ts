"use client";

import { useCallback, useTransition } from "react";
import { useLocale } from "next-intl";
import { useRouter } from "next/navigation";
import { updateLocalePreference } from "./actions";
import { isSupportedLocale } from "./locales.mjs";

/** Public contract for Task 25.3. Invalid values and storage failures never change UI locale. */
export function useLocalePreference() {
  const locale = useLocale();
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  const changeLocale = useCallback(async (requested: string): Promise<boolean> => {
    if (!isSupportedLocale(requested)) return false;

    try {
      const result = await updateLocalePreference(requested);
      if (!result.ok) return false;
      startTransition(() => router.refresh());
      return true;
    } catch {
      return false;
    }
  }, [router]);

  return { locale, changeLocale, isPending };
}
