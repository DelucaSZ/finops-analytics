import type { ReactNode } from "react";
import styles from "./flow-layout.module.css";

export default function FlowLayout({ children }: { children: ReactNode }) {
  return <div className={styles.scope}>{children}</div>;
}
