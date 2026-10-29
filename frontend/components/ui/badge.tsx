import type { HTMLAttributes, ReactNode } from "react";
import styles from "./primitives.module.css";
import { cx } from "./utils";

export type BadgeVariant = "neutral" | "info" | "success" | "warning" | "danger";
export type BadgeAppearance = "solid" | "outline" | "subtle";

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  appearance?: BadgeAppearance;
  icon?: ReactNode;
}

export function Badge({ variant = "neutral", appearance = "subtle", icon, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={cx(styles.badge, className)}
      data-aven-badge=""
      data-variant={variant}
      data-appearance={appearance}
      {...props}
    >
      {icon && <span aria-hidden="true">{icon}</span>}
      {children}
    </span>
  );
}
