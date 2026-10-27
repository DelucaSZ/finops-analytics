import { isValidElement, type HTMLAttributes, type ReactElement, type ReactNode } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  Skeleton,
} from "@/components/ui";
import styles from "./product-components.module.css";
import { TrendIndicator, type TrendIndicatorProps } from "./displays";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export type MetricTrend = TrendIndicatorProps | ReactElement<TrendIndicatorProps>;

export interface MetricCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  label: ReactNode;
  value: ReactNode | null | undefined;
  icon?: ReactNode;
  trend?: MetricTrend;
  supportingText?: ReactNode;
  status?: ReactNode;
  loading?: boolean;
  emptyValue?: ReactNode;
}

function renderTrend(trend: MetricTrend) {
  if (isValidElement(trend)) return trend;
  return <TrendIndicator {...trend} />;
}

export function MetricCard({
  label,
  value,
  icon,
  trend,
  supportingText,
  status,
  loading = false,
  emptyValue = "—",
  className,
  ...props
}: MetricCardProps) {
  return (
    <Card className={classNames(styles.metricCard, className)} {...props}>
      <CardHeader className={styles.metricHeader}>
        <div className={styles.metricLabelRow}>
          <span className={styles.metricLabel}>{label}</span>
          {icon && <span className={styles.metricIcon} aria-hidden="true">{icon}</span>}
        </div>
      </CardHeader>
      <CardContent className={styles.metricContent}>
        {loading ? (
          <div className={styles.metricLoading} role="status" aria-label="Loading metric">
            <Skeleton />
            <Skeleton />
          </div>
        ) : (
          <>
            <div className={styles.metricValue}>{value == null ? emptyValue : value}</div>
            {(trend || status) && (
              <div className={styles.metricMeta}>
                {trend && renderTrend(trend)}
                {status}
              </div>
            )}
            {supportingText && <div className={styles.metricSupporting}>{supportingText}</div>}
          </>
        )}
      </CardContent>
    </Card>
  );
}
