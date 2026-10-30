/* eslint-disable @next/next/no-img-element -- Official ambient SVGs must be served as external, non-optimized decorative assets. */
import type { ReactNode } from "react";
import { brand } from "@/lib/brand";
import styles from "./ambient-background.module.css";

export function AvenAmbientBackground({ children }: { children: ReactNode }) {
  return (
    <div className={styles.viewport}>
      <div className={styles.background} aria-hidden="true">
        <img
          className={`${styles.asset} ${styles.lightAsset}`}
          src={brand.assets.ambient.light}
          alt=""
          draggable={false}
        />
        <img
          className={`${styles.asset} ${styles.darkAsset}`}
          src={brand.assets.ambient.dark}
          alt=""
          draggable={false}
        />
      </div>
      <div className={styles.content}>{children}</div>
    </div>
  );
}
