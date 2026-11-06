"use client";

import { NextIntlClientProvider } from "next-intl";
import type { ReactNode } from "react";
import type { AppLocale } from "@/i18n/locales.mjs";
import { unavailableTranslation } from "@/i18n/fallback";
import type messages from "@/i18n/messages/pt-BR.json";

/** The initial snapshot comes from the same server request that rendered the HTML. */
export function LocaleProvider({
  children,
  locale,
  messages: initialMessages,
}: {
  children: ReactNode;
  locale: AppLocale;
  messages: typeof messages;
}) {
  return (
    <NextIntlClientProvider
      locale={locale}
      messages={initialMessages}
      onError={(error) => {
        if (process.env.NODE_ENV !== "production") console.error("[Aven i18n]", error);
      }}
      getMessageFallback={({ namespace, key }) => {
        if (process.env.NODE_ENV !== "production") {
          console.error("[Aven i18n] Missing translation:", [namespace, key].filter(Boolean).join("."));
        }
        return unavailableTranslation(locale);
      }}
    >
      {children}
    </NextIntlClientProvider>
  );
}
