import type { ReactNode } from "react";
import styles from "./collections-layout.module.css";

export default function CollectionsLayout({ children }: { children: ReactNode }) {
  return <div className={styles.scope}>{children}</div>;
}
