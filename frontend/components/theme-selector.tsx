"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/components/theme-provider";
import type { ThemePreference } from "@/lib/ui-preferences.mjs";

const options: Array<{
  value: ThemePreference;
  label: string;
  description: string;
  icon: typeof Monitor;
}> = [
  {
    value: "system",
    label: "Sistema",
    description: "Acompanha a preferência do dispositivo.",
    icon: Monitor,
  },
  {
    value: "light",
    label: "Claro",
    description: "Superfícies claras e contraste para ambientes iluminados.",
    icon: Sun,
  },
  {
    value: "dark",
    label: "Escuro",
    description: "Superfícies escuras com contraste reduzido.",
    icon: Moon,
  },
];

export function ThemeSelector() {
  const { theme, setTheme } = useTheme();

  return (
    <fieldset className="theme-selector">
      <legend>Tema</legend>
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
                name="deepops-theme"
                value={option.value}
                checked={theme === option.value}
                onChange={() => setTheme(option.value)}
              />
              <Icon size={18} aria-hidden="true" />
              <span>
                <strong>{option.label}</strong>
                <small>{option.description}</small>
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
