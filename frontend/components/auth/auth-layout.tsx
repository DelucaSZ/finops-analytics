import type { ReactNode } from "react";
import { BrandLogo } from "@/components/brand/brand-logo";
import { PRODUCT_TAGLINE } from "@/lib/brand";
import styles from "./auth-layout.module.css";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className={styles.page}>
      <section className={styles.brandPanel}>
        <div className={styles.brandContext}>
          <BrandLogo variant="wordmark" className={styles.brandLogo} />

          <div className={styles.brandCopy}>
            <p className={styles.brandEyebrow}>FINOPS MULTI-CLOUD</p>
            <p className={styles.brandTitle}>{PRODUCT_TAGLINE}</p>
            <p className={styles.brandPrinciple}>Complexidade por baixo. Clareza por cima.</p>
          </div>
        </div>
      </section>

      <section className={styles.formPanel} aria-label="Autenticação">
        <div className={styles.formFrame}>
          <div className={styles.mobileBrand}>
            <BrandLogo variant="wordmark" className={styles.mobileLogo} />
            <p>{PRODUCT_TAGLINE}</p>
          </div>
          {children}
        </div>
      </section>
    </main>
  );
}
