import { getRequestConfig } from "next-intl/server";
import { getLocaleMessages } from "./catalog";
import { unavailableTranslation } from "./fallback";
import { resolveServerLocale } from "./server";

export default getRequestConfig(async () => {
  const locale = await resolveServerLocale();
  return {
    locale,
    messages: getLocaleMessages(locale),
    onError(error) {
      if (process.env.NODE_ENV !== "production") {
        console.error("[Aven i18n] Translation error:", error);
      }
    },
    getMessageFallback({ namespace, key }) {
      if (process.env.NODE_ENV !== "production") {
        console.error("[Aven i18n] Missing translation:", [namespace, key].filter(Boolean).join("."));
      }
      return unavailableTranslation(locale);
    },
  };
});
