import type { HTMLAttributes } from "react";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface SkeletonProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: "text" | "rectangular" | "circle";
}

export function Skeleton({ variant = "text", className, ...props }: SkeletonProps) {
  return <span className={cx(styles.skeleton, className)} data-variant={variant} aria-hidden="true" {...props} />;
}
