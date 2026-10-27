import type { HTMLAttributes, ReactNode } from "react";
import styles from "./feedback.module.css";
import { cx } from "./utils";

export interface EmptyStateProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  primaryAction?: ReactNode;
  secondaryAction?: ReactNode;
}

export function EmptyState({ icon, title, description, primaryAction, secondaryAction, className, ...props }: EmptyStateProps) {
  return (
    <div className={cx(styles.emptyState, className)} {...props}>
      {icon && <span className={styles.emptyStateIcon} aria-hidden="true">{icon}</span>}
      <h3 className={styles.emptyStateTitle}>{title}</h3>
      {description && <p className={styles.emptyStateDescription}>{description}</p>}
      {(primaryAction || secondaryAction) && <div className={styles.emptyStateActions}>{primaryAction}{secondaryAction}</div>}
    </div>
  );
}
