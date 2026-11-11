"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import { useTranslations } from "next-intl";
import type { ThemePreference } from "@/lib/ui-preferences.mjs";

const options: Array<{
  value: ThemePreference;
  labelKey: "system" | "light" | "dark";
  descriptionKey: "systemDescription" | "lightDescription" | "darkDescription";
  icon: typeof Monitor;
}> = [
  {
    value: "system",
    labelKey: "system",
    descriptionKey: "systemDescription",
    icon: Monitor,
  },
  {
    value: "light",
    labelKey: "light",
    descriptionKey: "lightDescription",
    icon: Sun,
  },
  {
    value: "dark",
    labelKey: "dark",
    descriptionKey: "darkDescription",
    icon: Moon,
  },
];

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();
  const t = useTranslations("settings.appearance");

  return (
    <fieldset className="theme-selector">
      <legend>{t("fieldset")}</legend>
      <div className="theme-options">
        {options.map((option) => {
          const Icon = option.icon;
          return (
            <label
              className={theme === option.value ? "theme-option active" : "theme-option"}
              key={option.value}
            >
              <input
                type="radio"
                name="aven-theme"
                value={option.value}
                checked={theme === option.value}
                onChange={() => setTheme(option.value)}
              />
              <Icon size={18} aria-hidden="true" />
              <span>
                <strong>{t(option.labelKey)}</strong>
                <small>{t(option.descriptionKey)}</small>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
