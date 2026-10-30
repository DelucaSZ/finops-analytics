"use client";

import type { ReactNode } from "react";
import { AvenLogo, type AvenLogoSurface } from "@/components/brand/brand-logo";
import { useTheme } from "@/components/theme-provider";
import styles from "./auth-layout.module.css";

export function AuthLayout({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme();
  const surface: AvenLogoSurface = resolvedTheme === "dark" ? "dark" : "light";

  return (
    <main className={styles.page}>
      <section className={styles.brandPanel}>
        <div className={styles.brandHero}>
          <AvenLogo
            variant="vertical"
            surface={surface}
            priority
            className={styles.brandLogo}
          />
        </div>
      </section>

      <section className={styles.formPanel} aria-label="Autenticação">
        <div className={styles.formFrame}>
          <div className={styles.mobileBrand}>
            <AvenLogo
              variant="horizontal"
              surface={surface}
              priority
              className={styles.mobileLogo}
            />
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
