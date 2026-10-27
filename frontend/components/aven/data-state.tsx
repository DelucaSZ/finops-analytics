import type { HTMLAttributes, ReactNode } from "react";
import { Alert, EmptyState, Skeleton } from "@/components/ui";
import styles from "./product-components.module.css";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export interface DataStateProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  loading?: boolean;
  error?: ReactNode;
  empty?: boolean;
  emptyTitle?: ReactNode;
  emptyDescription?: ReactNode;
  emptyIcon?: ReactNode;
  emptyAction?: ReactNode;
  loadingFallback?: ReactNode;
  errorFallback?: ReactNode;
  children: ReactNode;
}

export function DataState({
  loading = false,
  error,
  empty = false,
  emptyTitle = "No data",
  emptyDescription,
  emptyIcon,
  emptyAction,
  loadingFallback,
  errorFallback,
  children,
  className,
  ...props
}: DataStateProps) {
  let content = children;

  if (loading) {
    content = loadingFallback ?? (
      <div className={styles.dataStateSkeleton} role="status" aria-label="Loading content">
        <Skeleton />
        <Skeleton />
        <Skeleton variant="rectangular" />
      </div>
    );
  } else if (error) {
    content = errorFallback ?? <Alert variant="danger" title="Unable to load data" description={error} />;
  } else if (empty) {
    content = (
      <EmptyState
        icon={emptyIcon}
        title={emptyTitle}
        description={emptyDescription}
        primaryAction={emptyAction}
      />
    );
  }

  return <div className={classNames(styles.dataState, className)} {...props}>{content}</div>;
}
