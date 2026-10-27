import type { ReactNode } from "react";
import { BrandLogo } from "@/components/brand/brand-logo";
import { PRODUCT_TAGLINE } from "@/lib/brand";
import styles from "./auth-layout.module.css";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className={styles.page}>
      <section className={styles.brandPanel} aria-label="Aven">
        <div className={styles.brandLogoSurface}>
          <BrandLogo variant="wordmark" />
        </div>

        <div className={styles.brandCopy}>
          <p className={styles.brandEyebrow}>FINOPS MULTI-CLOUD</p>
          <p className={styles.brandTitle}>{PRODUCT_TAGLINE}</p>
          <p className={styles.brandPrinciple}>Complexidade por baixo. Clareza por cima.</p>
        </div>
      </section>

      <section className={styles.formPanel} aria-label="Autenticação">
        <div className={styles.formFrame}>
          <div className={styles.mobileBrand}>
            <div className={styles.brandLogoSurface}>
              <BrandLogo variant="wordmark" />
            </div>
            <p>{PRODUCT_TAGLINE}</p>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
