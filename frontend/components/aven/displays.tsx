import {
  AlertCircle,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  CheckCircle2,
  Circle,
  Clock3,
  Info,
  Minus,
} from "lucide-react";
import type { HTMLAttributes, ReactNode } from "react";
import { Badge, type BadgeVariant } from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import styles from "./product-components.module.css";
import type { ProductStatus, TrendDirection, TrendSentiment } from "./types";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export interface CurrencyDisplayProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  value: number | null | undefined;
  currency: string;
  locale?: string;
  compact?: boolean;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  currencyDisplay?: "symbol" | "narrowSymbol" | "code" | "name";
  nullDisplay?: ReactNode;
}

export function CurrencyDisplay({
  value,
  currency,
  locale = "en-US",
  compact = false,
  minimumFractionDigits,
  maximumFractionDigits,
  currencyDisplay = "symbol",
  nullDisplay = "—",
  className,
  ...props
}: CurrencyDisplayProps) {
  if (value == null) {
    return <span className={classNames(styles.numeric, className)} {...props}>{nullDisplay}</span>;
  }

  const formatted = new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    currencyDisplay,
    notation: compact ? "compact" : "standard",
    minimumFractionDigits,
    maximumFractionDigits,
  }).format(value);

  return <span className={classNames(styles.numeric, className)} {...props}>{formatted}</span>;
}

export interface PercentageDisplayProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  value: number | null | undefined;
  valueMode?: "percent" | "fraction";
  locale?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  signDisplay?: "auto" | "always" | "exceptZero" | "never";
  nullDisplay?: ReactNode;
}

export function PercentageDisplay({
  value,
  valueMode = "percent",
  locale = "en-US",
  minimumFractionDigits,
  maximumFractionDigits = 2,
  signDisplay = "auto",
  nullDisplay = "—",
  className,
  ...props
}: PercentageDisplayProps) {
  if (value == null) {
    return <span className={classNames(styles.numeric, className)} {...props}>{nullDisplay}</span>;
  }

  const normalized = valueMode === "percent" ? value / 100 : value;
  const formatted = new Intl.NumberFormat(locale, {
    style: "percent",
    minimumFractionDigits,
    maximumFractionDigits,
    signDisplay,
  }).format(normalized);

  return <span className={classNames(styles.numeric, className)} {...props}>{formatted}</span>;
}

export interface TrendIndicatorProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  value: number | string;
  direction: TrendDirection;
  sentiment: TrendSentiment;
  unit?: "percent" | "none";
  locale?: string;
  maximumFractionDigits?: number;
  label?: string;
}

const trendIcons = {
  up: ArrowUp,
  down: ArrowDown,
  flat: Minus,
} as const;

const trendVariants: Record<TrendSentiment, BadgeVariant> = {
  positive: "success",
  negative: "danger",
  neutral: "neutral",
};

export function TrendIndicator({
  value,
  direction,
  sentiment,
  unit = "percent",
  locale = "en-US",
  maximumFractionDigits = 2,
  label = "Trend",
  className,
  ...props
}: TrendIndicatorProps) {
  const Icon = trendIcons[direction];
  const formattedValue = typeof value === "number"
    ? unit === "percent"
      ? new Intl.NumberFormat(locale, {
          style: "percent",
          maximumFractionDigits,
        }).format(Math.abs(value) / 100)
      : new Intl.NumberFormat(locale, { maximumFractionDigits }).format(Math.abs(value))
    : value;
  const accessibleDirection = direction === "flat" ? "flat" : direction;
  const accessibleLabel = `${label}: ${accessibleDirection}, ${sentiment}, ${formattedValue}`;

  return (
    <span className={classNames(styles.inlineDisplay, className)} aria-label={accessibleLabel} {...props}>
      <Badge variant={trendVariants[sentiment]} icon={<Icon {...iconDefaults} />}>
        {formattedValue}
      </Badge>
    </span>
  );
}

const statusVariants: Record<ProductStatus, BadgeVariant> = {
  neutral: "neutral",
  info: "info",
  success: "success",
  warning: "warning",
  danger: "danger",
  pending: "info",
};

const statusIcons = {
  neutral: Circle,
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertCircle,
  pending: Clock3,
} as const;

export interface StatusIndicatorProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  status: ProductStatus;
  label: ReactNode;
  variant?: BadgeVariant;
  icon?: ReactNode;
}

export function StatusIndicator({ status, label, variant, icon, className, ...props }: StatusIndicatorProps) {
  const Icon = statusIcons[status];
  return (
    <span className={classNames(styles.inlineDisplay, className)} {...props}>
      <Badge variant={variant ?? statusVariants[status]} icon={icon ?? <Icon {...iconDefaults} />}>
        {label}
      </Badge>
    </span>
  );
}

const providerLabels: Record<string, string> = {
  aws: "AWS",
  oci: "OCI",
};

export interface ProviderBadgeProps extends Omit<HTMLAttributes<HTMLSpanElement>, "children"> {
  provider: string;
  label?: ReactNode;
  icon?: ReactNode;
  variant?: BadgeVariant;
}

export function ProviderBadge({
  provider,
  label,
  icon,
  variant = "neutral",
  className,
  ...props
}: ProviderBadgeProps) {
  const normalized = provider.trim().toLowerCase();
  const displayLabel = label ?? providerLabels[normalized] ?? provider;
  return (
    <span className={classNames(styles.inlineDisplay, className)} data-provider={normalized} {...props}>
      <Badge variant={variant} icon={icon}>{displayLabel}</Badge>
    </span>
  );
}
