import type { HTMLAttributes } from "react";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface DividerProps extends HTMLAttributes<HTMLHRElement> {
  orientation?: "horizontal" | "vertical";
}

export function Divider({ orientation = "horizontal", className, ...props }: DividerProps) {
  return <hr className={cx(styles.divider, className)} data-orientation={orientation} aria-orientation={orientation} {...props} />;
}
