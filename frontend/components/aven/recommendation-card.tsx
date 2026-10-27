import type { HTMLAttributes, ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui";
import styles from "./product-components.module.css";
import { ProviderBadge, StatusIndicator } from "./displays";
import type { ProductStatus } from "./types";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export interface RecommendationCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  resource?: ReactNode;
  provider?: string;
  providerLabel?: ReactNode;
  impact?: ReactNode;
  potentialSavings?: ReactNode;
  confidence?: ReactNode;
  status?: ProductStatus;
  statusLabel?: ReactNode;
  metadata?: ReactNode;
  actions?: ReactNode;
}

export function RecommendationCard({
  title,
  description,
  resource,
  provider,
  providerLabel,
  impact,
  potentialSavings,
  confidence,
  status,
  statusLabel,
  metadata,
  actions,
  className,
  ...props
}: RecommendationCardProps) {
  return (
    <Card className={classNames(styles.recommendationCard, className)} {...props}>
      <CardHeader>
        <div className={styles.cardHeaderRow}>
          <div className={styles.cardHeaderCopy}>
            <CardTitle>{title}</CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          <div className={styles.recommendationBadges}>
            {provider && <ProviderBadge provider={provider} label={providerLabel} />}
            {status && statusLabel && <StatusIndicator status={status} label={statusLabel} />}
          </div>
        </div>
      </CardHeader>
      <CardContent className={styles.recommendationContent}>
        {(potentialSavings || impact || confidence) && (
          <div className={styles.recommendationMetrics}>
            {potentialSavings && (
              <div className={styles.recommendationMetric}>
                <span className={styles.recommendationMetricLabel}>Potential savings</span>
                <span className={styles.recommendationSavings}>{potentialSavings}</span>
              </div>
            )}
            {impact && (
              <div className={styles.recommendationMetric}>
                <span className={styles.recommendationMetricLabel}>Impact</span>
                <span className={styles.recommendationMetricValue}>{impact}</span>
              </div>
            )}
            {confidence && (
              <div className={styles.recommendationMetric}>
                <span className={styles.recommendationMetricLabel}>Confidence</span>
                <span className={styles.recommendationMetricValue}>{confidence}</span>
              </div>
            )}
          </div>
        )}
        {resource && (
          <div className={styles.recommendationResource}>
            <span className={styles.recommendationMetricLabel}>Resource</span>
            {resource}
          </div>
        )}
        {metadata && <div className={styles.recommendationMetadata}>{metadata}</div>}
      </CardContent>
      {actions && <CardFooter className={styles.recommendationActions}>{actions}</CardFooter>}
    </Card>
  );
}
