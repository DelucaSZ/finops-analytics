"use client";

import Image from "next/image";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { Check, ChevronDown } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui";
import { useLocalePreference } from "@/i18n/use-locale-preference";
import type { AppLocale } from "@/i18n/locales.mjs";
import { iconDefaults, iconSizes } from "@/lib/iconography";
import styles from "./app-shell.module.css";

const options: ReadonlyArray<{
  locale: AppLocale;
  flag: string;
  code: string;
  nameKey: "portugueseBrazil" | "englishUnitedStates";
}> = [
  { locale: "pt-BR", flag: "/flags/br.svg", code: "PT-BR", nameKey: "portugueseBrazil" },
  { locale: "en-US", flag: "/flags/us.svg", code: "EN-US", nameKey: "englishUnitedStates" },
];

function Flag({ src }: { src: string }) {
  return <Image src={src} alt="" aria-hidden="true" width={32} height={24} className={styles.languageFlag} />;
}

export function LanguageControl() {
  const t = useTranslations("shell.language");
  const { locale, changeLocale, isPending } = useLocalePreference();
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const current = options.find((item) => item.locale === locale) ?? options[0];

  async function selectLocale(requested: AppLocale) {
    if (requested === locale) {
      setOpen(false);
      return;
    }
    setFailed(false);
    const ok = await changeLocale(requested);
    if (ok) setOpen(false);
    else setFailed(true);
  }

  return (
    <DropdownMenu open={open} onOpenChange={(nextOpen) => {
      setOpen(nextOpen);
      if (!nextOpen) setFailed(false);
    }}>
      <DropdownMenuTrigger
        className={styles.topbarControl}
        disabled={isPending}
        aria-label={t("current", { language: t(current.nameKey) })}
      >
        <Flag src={current.flag} />
        <span className={styles.topbarControlLabel}>{current.code}</span>
        <ChevronDown {...iconDefaults} size={iconSizes.sm} aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent aria-label={t("select")} aria-busy={isPending}>
        {options.map((option) => {
          const selected = option.locale === locale;
          return (
            <DropdownMenuItem
              key={option.locale}
              role="menuitemradio"
              aria-checked={selected}
              disabled={isPending}
              onClick={(event) => {
                event.preventDefault();
                void selectLocale(option.locale);
              }}
            >
              <span className={styles.languageOption}>
                <Flag src={option.flag} />
                <span>{t(option.nameKey)}</span>
                {selected && <Check {...iconDefaults} size={iconSizes.sm} className={styles.languageSelected} aria-hidden="true" />}
              </span>
            </DropdownMenuItem>
          );
        })}
        {failed && <p role="alert" className={styles.languageError}>{t("changeFailed")}</p>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
