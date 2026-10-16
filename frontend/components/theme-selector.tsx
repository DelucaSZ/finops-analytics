"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import {
  normalizeThemePreference,
  resolveThemePreference,
  THEME_STORAGE_KEY,
  type ThemePreference,
} from "@/lib/ui-preferences.mjs";

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

function applyTheme(preference: ThemePreference) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  const resolved = resolveThemePreference(preference, media.matches);
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
}

export function ThemeSelector() {
  const [preference, setPreference] = useState<ThemePreference>("system");

  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    } catch {
      stored = null;
    }
    const saved = normalizeThemePreference(stored);
    setPreference(saved);
    applyTheme(saved);
  }, []);

  function updateTheme(next: ThemePreference) {
    setPreference(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      // A preferência continua válida para a sessão mesmo se storage estiver indisponível.
    }
    applyTheme(next);
    window.dispatchEvent(new CustomEvent("deepops:theme-change", { detail: next }));
  }

  return (
    <fieldset className="theme-selector">
      <legend>Tema</legend>
      <div className="theme-options">
        {options.map((option) => {
          const Icon = option.icon;
          return (
            <label
              className={preference === option.value ? "theme-option active" : "theme-option"}
              key={option.value}
            >
              <input
                type="radio"
                name="deepops-theme"
                value={option.value}
                checked={preference === option.value}
                onChange={() => updateTheme(option.value)}
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
