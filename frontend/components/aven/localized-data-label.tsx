"use client";

import { useTranslations } from "next-intl";

/** Dedicated client label keeps noninteractive layout components server-compatible. */
export function LocalizedDataLabel({ id }: { id: "noChartData" }) {
  const t = useTranslations("common.dataState");
  return <>{t(id)}</>;
}
