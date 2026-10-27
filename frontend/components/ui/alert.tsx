import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { iconDefaults } from "@/lib/iconography";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export type AlertVariant = "info" | "success" | "warning" | "danger";

const alertIcons = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
} as const;

export interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: AlertVariant;
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  icon?: ReactNode;
}

export function Alert({ variant = "info", title, description, actions, icon, className, children, ...props }: AlertProps) {
  const Icon = alertIcons[variant];
  return (
    <div className={cx(styles.alert, className)} data-variant={variant} role={variant === "danger" ? "alert" : "status"} {...props}>
      <span className={styles.alertIcon} aria-hidden="true">{icon ?? <Icon {...iconDefaults} />}</span>
      <div className={styles.alertContent}>
        {title && <p className={styles.alertTitle}>{title}</p>}
        {description && <p className={styles.alertDescription}>{description}</p>}
        {children}
        {actions && <div className={styles.alertActions}>{actions}</div>}
      </div>
    </div>
  );
}
