import type { HTMLAttributes, ReactNode } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Surface,
} from "@/components/ui";
import styles from "./product-components.module.css";
import { DataState } from "./data-state";

function classNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

export type PageWidth = "standard" | "wide" | "full";

export interface PageContainerProps extends HTMLAttributes<HTMLDivElement> {
  width?: PageWidth;
  children: ReactNode;
}

export function PageContainer({
  width = "wide",
  className,
  children,
  ...props
}: PageContainerProps) {
  return (
    <div
      {...props}
      className={className}
      data-aven-page-container=""
      data-width={width}
    >
      {children}
    </div>
  );
}

export type LayoutGap = "compact" | "default" | "section" | "page";

export interface StackProps extends HTMLAttributes<HTMLDivElement> {
  gap?: LayoutGap;
  children: ReactNode;
}

export function Stack({ gap = "default", className, children, ...props }: StackProps) {
  return (
    <div {...props} className={className} data-aven-stack="" data-gap={gap}>
      {children}
    </div>
  );
}

export interface ClusterProps extends HTMLAttributes<HTMLDivElement> {
  gap?: LayoutGap;
  children: ReactNode;
}

export function Cluster({ gap = "default", className, children, ...props }: ClusterProps) {
  return (
    <div {...props} className={className} data-aven-cluster="" data-gap={gap}>
      {children}
    </div>
  );
}

export type GridVariant = "auto" | "metrics" | "content" | "split";

export interface GridProps extends HTMLAttributes<HTMLDivElement> {
  variant?: GridVariant;
  children: ReactNode;
}

export function Grid({ variant = "auto", className, children, ...props }: GridProps) {
  return (
    <div {...props} className={className} data-aven-grid={variant}>
      {children}
    </div>
  );
}

export interface PageHeaderProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  breadcrumbs?: ReactNode;
  actions?: ReactNode;
  metadata?: ReactNode;
}

export function PageHeader({
  title,
  description,
  breadcrumbs,
  actions,
  metadata,
  className,
  ...props
}: PageHeaderProps) {
  return (
    <header className={classNames(styles.pageHeader, className)} data-aven-page-header="" {...props}>
      {breadcrumbs && <div className={styles.breadcrumbs}>{breadcrumbs}</div>}
      <div className={styles.pageHeaderMain}>
        <div className={styles.pageHeaderCopy}>
          <h1 className={styles.pageTitle}>{title}</h1>
          {description && <p className={styles.pageDescription}>{description}</p>}
          {metadata && <div className={styles.pageMetadata}>{metadata}</div>}
        </div>
        {actions && <div className={styles.pageActions}>{actions}</div>}
      </div>
    </header>
  );
}

export interface SectionProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  appearance?: "plain" | "card";
  children: ReactNode;
}

export function Section({
  title,
  description,
  actions,
  appearance = "plain",
  children,
  className,
  ...props
}: SectionProps) {
  const heading = title || description || actions ? (
    <div className={styles.sectionHeader}>
      <div className={styles.sectionCopy}>
        {title && <h2 className={styles.sectionTitle}>{title}</h2>}
        {description && <p className={styles.sectionDescription}>{description}</p>}
      </div>
      {actions && <div className={styles.sectionActions}>{actions}</div>}
    </div>
  ) : null;

  if (appearance === "card") {
    return (
      <Surface as="section" variant="section" data-aven-section="" className={classNames(styles.sectionCard, className)} {...props}>
        {heading && <CardHeader className={styles.sectionCardHeader}>{heading}</CardHeader>}
        <CardContent className={styles.sectionCardContent}>{children}</CardContent>
      </Surface>
    );
  }

  return (
    <section className={classNames(styles.section, className)} data-aven-section="" {...props}>
      {heading}
      <div className={styles.sectionContent}>{children}</div>
    </section>
  );
}

export type FilterItemSize = "compact" | "default" | "wide" | "fluid";

export interface FilterItemProps extends HTMLAttributes<HTMLDivElement> {
  size?: FilterItemSize;
}

export function FilterItem({ size = "default", className, children, ...props }: FilterItemProps) {
  return (
    <div
      {...props}
      className={classNames(styles.filterItem, className)}
      data-aven-filter-item=""
      data-size={size}
    >
      {children}
    </div>
  );
}

export interface FilterBarProps extends Omit<HTMLAttributes<HTMLDivElement>, "children"> {
  children: ReactNode;
  secondary?: ReactNode;
  summary?: ReactNode;
  actions?: ReactNode;
  clearAction?: ReactNode;
  surface?: boolean;
}

function FilterBarContent({
  children,
  secondary,
  summary,
  actions,
  clearAction,
}: Pick<FilterBarProps, "children" | "secondary" | "summary" | "actions" | "clearAction">) {
  return (
    <div className={styles.filterBar} data-aven-filter-bar="">
      <div className={styles.filterPrimary} data-aven-filter-group="primary">{children}</div>
      {secondary && (
        <div className={styles.filterSecondary} data-aven-filter-group="secondary">{secondary}</div>
      )}
      {(clearAction || actions) && (
        <div className={styles.filterActions} data-aven-filter-actions="">{clearAction}{actions}</div>
      )}
      {summary && <div className={styles.filterSummary}>{summary}</div>}
    </div>
  );
}

export function FilterBar({
  children,
  secondary,
  summary,
  actions,
  clearAction,
  surface = true,
  className,
  ...props
}: FilterBarProps) {
  if (surface) {
    return (
      <Surface variant="panel" className={classNames(styles.filterSurface, className)} {...props}>
        <CardContent className={styles.filterSurfaceContent}>
          <FilterBarContent secondary={secondary} summary={summary} actions={actions} clearAction={clearAction}>
            {children}
          </FilterBarContent>
        </CardContent>
      </Surface>
    );
  }

  return (
    <div className={classNames(styles.filterSurfacePlain, className)} {...props}>
      <FilterBarContent secondary={secondary} summary={summary} actions={actions} clearAction={clearAction}>
        {children}
      </FilterBarContent>
    </div>
  );
}

export interface ChartCardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  legend?: ReactNode;
  children: ReactNode;
  loading?: boolean;
  error?: ReactNode;
  empty?: boolean;
  emptyTitle?: ReactNode;
  emptyDescription?: ReactNode;
}

export function ChartCard({
  title,
  description,
  actions,
  legend,
  children,
  loading = false,
  error,
  empty = false,
  emptyTitle = "No chart data",
  emptyDescription,
  className,
  ...props
}: ChartCardProps) {
  return (
    <Card className={classNames(styles.chartCard, className)} {...props}>
      <CardHeader>
        <div className={styles.cardHeaderRow}>
          <div className={styles.cardHeaderCopy}>
            <CardTitle>{title}</CardTitle>
            {description && <CardDescription>{description}</CardDescription>}
          </div>
          {actions && <div className={styles.cardHeaderActions}>{actions}</div>}
        </div>
        {legend && <div className={styles.chartLegend}>{legend}</div>}
      </CardHeader>
      <CardContent className={styles.chartContent}>
        <DataState
          loading={loading}
          error={error}
          empty={empty}
          emptyTitle={emptyTitle}
          emptyDescription={emptyDescription}
        >
          {children}
        </DataState>
      </CardContent>
    </Card>
  );
}
