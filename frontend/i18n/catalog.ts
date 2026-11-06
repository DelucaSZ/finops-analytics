import ptBR from "./messages/pt-BR.json";
import enUS from "./messages/en-US.json";
import { DEFAULT_LOCALE, type AppLocale } from "./locales.mjs";

type CatalogObject = Record<string, unknown>;

/** A missing en-US leaf falls back to its pt-BR counterpart. CI still rejects catalogue drift. */
function mergeWithDefault(defaults: CatalogObject, selected: CatalogObject): CatalogObject {
  return Object.fromEntries(Object.entries(defaults).map(([key, value]) => {
    const candidate = selected[key];
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      const nested = candidate !== null && typeof candidate === "object" && !Array.isArray(candidate)
        ? candidate as CatalogObject : {};
      return [key, mergeWithDefault(value as CatalogObject, nested)];
    }
    return [key, typeof candidate === "string" && candidate.length > 0 ? candidate : value];
  }));
}

export function getLocaleMessages(locale: AppLocale): typeof ptBR {
  if (locale === DEFAULT_LOCALE) return ptBR;
  return mergeWithDefault(ptBR, enUS) as typeof ptBR;
}
