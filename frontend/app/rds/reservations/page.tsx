"use client";

import { Suspense, useMemo, type ReactNode } from "react";
import { useLocale, useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { AlertTriangle, Cloud, Gauge, RefreshCw, ShieldCheck, TimerReset } from "lucide-react";
import {
  AccountSelector,
  ChartCard,
  DataState,
  FilterBar,
  MetricCard,
  PageHeader,
  PercentageDisplay,
  ProviderBadge,
  ResourceIdentifier,
  Section,
  StatusIndicator,
} from "@/components/aven";
import {
  Alert,
  Button,
  Pagination,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { ApiError } from "@/lib/api";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy } from "@/lib/query-keys.mjs";
import type {
  RdsCoverageItem,
  RdsPage,
  RdsReservationOpportunity,
  RdsReservationsOperationalStatus,
  RdsReservationsOptions,
  RdsReservationsSummary,
  RdsReservationUtilization,
} from "@/lib/rds-reservations";
import {
  buildRdsDashboardQuery,
  coverageStatusLabel,
  formatNu,
  opportunityTypeLabel,
  parseRdsReservationSearchParams,
  patchRdsReservationUrl,
} from "@/lib/rds-reservations-query.mjs";
import type { RdsReservationQueryState } from "@/lib/rds-reservations-query.mjs";
import { useApiQuery } from "@/lib/server-state";
import styles from "./rds-reservations.module.css";

function useTabLabels(): Record<RdsReservationQueryState["tab"], string> {
  const t = useTranslations("reservations");
  return { coverage:t("tabs.coverage"), reservations:t("tabs.reservations"), expiring:t("tabs.expiring"), opportunities:t("tabs.opportunities") };
}

function useExpirationLabels(): Record<string,string> {
  const t = useTranslations("reservations");
  return {LE_7:t("expiration.le7"),LE_15:t("expiration.le15"),LE_30:t("expiration.le30"),GT_30:t("expiration.gt30"),EXPIRED:t("expiration.expired")};
}

function formatDate(value?: string | null, locale = "pt-BR") {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function formatDateTime(value?: string | null, locale = "pt-BR") {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat(locale, {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function humanize(value?: string | null) {
  if (!value) return "—";
  return value.toLowerCase().split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");
}

function useQueryError() {
  const t = useTranslations("reservations");
  return (error: unknown, fallback: string) => {
  if (!(error instanceof ApiError)) return fallback;
  if (error.code === "RDS_COVERAGE_NOT_CALCULATED" || error.status === 404) return t("errors.notCalculated");
  if (error.status === 403) return t("errors.forbidden");
  if (error.status === 429) return t("errors.rateLimit");
  if (error.status === 400) return t("errors.rejected");
  if (error.status === 502 || error.status === 503) return t("errors.providerUnavailable");
  return fallback;
  };
}

function operationalTone(status?: RdsReservationsOperationalStatus["pipeline_status"]) {
  if (status === "COMPLETED") return "success" as const;
  if (status === "RUNNING") return "pending" as const;
  if (status === "FAILED") return "danger" as const;
  if (status === "STALE" || status === "COMPLETED_WITH_WARNINGS") return "warning" as const;
  return "neutral" as const;
}

function OperationalNotice({ status }: { status?: RdsReservationsOperationalStatus }) {
  const t = useTranslations("reservations");
  if (!status) return null;
  if (status.pipeline_status === "NEVER_EXECUTED") {
    return <Alert variant="warning" title={t("pipeline.neverTitle")} description={t("pipeline.neverDescription")} />;
  }
  if (status.pipeline_status === "RUNNING") {
    return <Alert variant="info" title={t("pipeline.runningTitle")} description={t("pipeline.runningDescription", { stage: status.pipeline_stage ? ` (${humanize(status.pipeline_stage)})` : "" })} />;
  }
  if (status.pipeline_status === "FAILED") {
    return <Alert variant="danger" title={t("pipeline.failedTitle")} description={status.coverage_run_id ? t("pipeline.failedWithSnapshot") : t("pipeline.failedNoSnapshot")} />;
  }
  if (status.pipeline_status === "STALE") {
    return <Alert variant="warning" title={t("pipeline.staleTitle")} description={t("pipeline.staleDescription", { hours: status.freshness_threshold_hours })} />;
  }
  if (status.pipeline_status === "COMPLETED_WITH_WARNINGS") {
    return <Alert variant="warning" title={t("pipeline.warningTitle")} description={t("pipeline.warningDescription")} />;
  }
  return null;
}

function coverageTone(status: string) {
  if (status === "FULL") return "success" as const;
  if (status === "PARTIAL") return "warning" as const;
  if (status === "UNCOVERED") return "danger" as const;
  return "neutral" as const;
}

function reservationTone(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "active") return "success" as const;
  if (normalized.includes("pending")) return "pending" as const;
  return "neutral" as const;
}

function expirationState(item: RdsReservationUtilization) {
  if (item.expiration_band === "EXPIRED" || item.days_remaining < 0) return { status: "danger" as const, label: "Expired" };
  if (item.expiration_severity === "high") return { status: "danger" as const, label: "Expiring soon" };
  return { status: "warning" as const, label: "Expiring" };
}



function accountOptions(options?: RdsReservationsOptions) {
  return (options?.accounts ?? []).map((account) => ({
    value: account.account_id,
    label: account.name || account.account_id,
    accountId: account.account_id,
    provider: "AWS",
    searchTerms: [account.account_id, account.name || ""],
  }));
}

function selectOptions(values: string[] | undefined) {
  return (values ?? []).map((value) => ({ value, label: value }));
}

function TableState({ loading, error, empty, emptyTitle, emptyDescription, colSpan }: {
  loading: boolean;
  error?: string;
  empty: boolean;
  emptyTitle: string;
  emptyDescription: string;
  colSpan: number;
}) {
  const t = useTranslations("reservations");
  if (loading) {
    return (
      <TableBody>
        {Array.from({ length: 5 }, (_, index) => (
          <TableRow key={index} staticRow><TableCell colSpan={colSpan}><Skeleton /></TableCell></TableRow>
        ))}
      </TableBody>
    );
  }
  if (error) {
    return <TableBody><TableRow staticRow><TableCell colSpan={colSpan}><Alert variant="danger" title={t("states.loadError")} description={error} /></TableCell></TableRow></TableBody>;
  }
  if (empty) {
    return <TableBody><TableRow staticRow><TableCell colSpan={colSpan}><DataState empty emptyTitle={emptyTitle} emptyDescription={emptyDescription}><span /></DataState></TableCell></TableRow></TableBody>;
  }
  return null;
}

function CoverageSummary({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const t = useTranslations("reservations");
  const total = summary?.rds.total ?? 0;
  const groups = [
    [t("coverage.fullShort"), summary?.rds.fully_covered ?? 0, styles.full],
    [t("coverage.partialShort"), summary?.rds.partially_covered ?? 0, styles.partial],
    [t("coverage.uncovered"), summary?.rds.uncovered ?? 0, styles.uncovered],
    [t("coverage.unknown"), summary?.rds.unknown ?? 0, styles.unknown],
  ] as const;
  return (
    <ChartCard title={t("coverage.distribution")} description={t("coverage.chartDescription")} loading={loading} empty={!loading && total === 0} emptyTitle={t("coverage.noWorkloads")} emptyDescription={t("coverage.noEligible")} legend={(
      <div className={styles.legend}>{groups.map(([label, value, tone]) => <span className={styles.legendItem} key={label}><span className={`${styles.dot} ${tone}`} aria-hidden="true" />{label}<strong>{value}</strong></span>)}</div>
    )}>
      <div className={styles.distribution} role="img" aria-label={t("coverage.chartAria",{values:groups.map(([label, value]) => `${label} ${value}`).join(", ")})}>
        {groups.map(([label, value, tone]) => value > 0 ? <span key={label} className={`${styles.segment} ${tone}`} style={{ inlineSize: `${(value / total) * 100}%` }} title={`${label}: ${value}`} /> : null)}
      </div>
    </ChartCard>
  );
}

function CapacitySummary({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const t = useTranslations("reservations");
  return (
    <Section appearance="card" title={t("capacity.title")} description={t("capacity.description")}>
      <DataState loading={loading}>
        <div className={styles.capacityGrid}>
          <div className={styles.capacityPrimary}><span>{t("capacity.utilization")}</span><strong><PercentageDisplay value={summary?.reservations.utilization_percentage} /></strong><small>{formatNu(summary?.reservations.used_units ?? 0)} / {formatNu(summary?.reservations.reserved_units ?? 0)}</small></div>
          <div><span>{t("capacity.reserved")}</span><strong>{formatNu(summary?.reservations.reserved_units ?? 0)}</strong></div>
          <div><span>{t("capacity.allocated")}</span><strong>{formatNu(summary?.reservations.used_units ?? 0)}</strong></div>
          <div><span>{t("capacity.unused")}</span><strong>{formatNu(summary?.reservations.unused_units ?? 0)}</strong></div>
        </div>
      </DataState>
    </Section>
  );
}

function Filters({ state, options, loading, onChange, onClear }: {
  state: RdsReservationQueryState;
  options?: RdsReservationsOptions;
  loading: boolean;
  onChange: (changes: Partial<RdsReservationQueryState>) => void;
  onClear: () => void;
}) {
  const t = useTranslations("reservations");
  const expirationLabels = useExpirationLabels();
  const coverageLabels: Record<string,string> = { FULL:t("coverage.full"), PARTIAL:t("coverage.partial"), UNCOVERED:t("coverage.uncovered"), UNKNOWN:t("coverage.unknown") };
  const opportunityLabels: Record<string,string> = {RDS_RESERVATION_UNCOVERED:t("opportunityTypes.uncovered"),RDS_RESERVATION_PARTIAL_COVERAGE:t("opportunityTypes.partial"),RDS_RESERVATION_UNUSED_CAPACITY:t("opportunityTypes.unused"),RDS_RESERVATION_EXPIRING:t("opportunityTypes.expiring")};
  return (
    <FilterBar aria-label={t("filters.aria")} actions={<Button variant="ghost" size="sm" onClick={onClear}>{t("actions.clear")}</Button>}>
      <AccountSelector label={t("filters.account")} value={state.account} onChange={(account) => onChange({ account, page: 1 })} options={accountOptions(options)} loading={loading} placeholder={t("filters.allAccounts")} clearLabel={t("filters.allAccounts")} />
      <Select label={t("filters.region")} value={state.region} onChange={(event) => onChange({ region: event.target.value, page: 1 })} options={selectOptions(options?.regions)} placeholder={t("filters.allRegions")} />
      <Select label={t("filters.engine")} value={state.engine} onChange={(event) => onChange({ engine: event.target.value, page: 1 })} options={selectOptions(options?.engines)} placeholder={t("filters.allEngines")} />
      <Select label={t("filters.family")} value={state.family} onChange={(event) => onChange({ family: event.target.value, page: 1 })} options={selectOptions(options?.families)} placeholder={t("filters.allFamilies")} />
      <Select label={t("filters.class")} value={state.instanceClass} onChange={(event) => onChange({ instanceClass: event.target.value, page: 1 })} options={selectOptions(options?.instance_classes)} placeholder={t("filters.allClasses")} />
      {state.tab === "coverage" && <Select label={t("filters.coverage")} value={state.coverageStatus} onChange={(event) => onChange({ coverageStatus: event.target.value, page: 1 })} options={["FULL", "PARTIAL", "UNCOVERED", "UNKNOWN"].map((value) => ({ value, label: coverageLabels[value] ?? coverageStatusLabel(value) }))} placeholder={t("filters.allStatuses")} />}
      {(state.tab === "reservations" || state.tab === "expiring") && <Select label={t("filters.expiration")} value={state.expirationRange} onChange={(event) => onChange({ expirationRange: event.target.value, page: 1 })} options={Object.entries(expirationLabels).map(([value, label]) => ({ value, label }))} placeholder={state.tab === "expiring" ? t("expiration.le30") : t("filters.allExpirations")} />}
      {state.tab === "opportunities" && <Select label={t("filters.opportunity")} value={state.opportunityType} onChange={(event) => onChange({ opportunityType: event.target.value, page: 1 })} options={["RDS_RESERVATION_UNCOVERED", "RDS_RESERVATION_PARTIAL_COVERAGE", "RDS_RESERVATION_UNUSED_CAPACITY", "RDS_RESERVATION_EXPIRING"].map((value) => ({ value, label: opportunityLabels[value] ?? opportunityTypeLabel(value) }))} placeholder={t("filters.allOpportunityTypes")} />}
    </FilterBar>
  );
}

function CoverageTable({ page, loading, error }: { page?: RdsPage<RdsCoverageItem>; loading: boolean; error?: string }) {
  const t = useTranslations("reservations");
  const coverageLabels: Record<string,string> = {FULL:t("coverage.full"),PARTIAL:t("coverage.partial"),UNCOVERED:t("coverage.uncovered"),UNKNOWN:t("coverage.unknown")};
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>{t("table.resource")}</TableHead><TableHead>{t("table.technology")}</TableHead><TableHead>{t("table.accountRegion")}</TableHead><TableHead numeric>{t("table.coverage")}</TableHead><TableHead>{t("table.status")}</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle={t("table.noCoverage")} emptyDescription={t("table.noCoverageDescription")} colSpan={5} /> : (
        <TableBody>{items.map((item) => <TableRow key={item.instance_id}><TableCell><ResourceIdentifier primary={item.instance} copyValue={item.instance} /><span className={styles.secondary}>{item.instance_class}</span></TableCell><TableCell>{item.engine}<span className={styles.secondary}>{item.engine_version || t("table.versionUnavailable")}</span></TableCell><TableCell>{item.account.name || item.account.account_id}<span className={styles.secondary}>{item.region}</span></TableCell><TableCell numeric><PercentageDisplay value={item.coverage_percentage} /><span className={styles.secondary}>{formatNu(item.covered_units)} / {formatNu(item.required_units)}</span></TableCell><TableCell><StatusIndicator status={coverageTone(item.coverage_status)} label={coverageLabels[item.coverage_status] ?? coverageStatusLabel(item.coverage_status)} /></TableCell></TableRow>)}</TableBody>
      )}
    </Table>
  );
}

function ReservationsTable({ page, loading, error, expiring = false }: { page?: RdsPage<RdsReservationUtilization>; loading: boolean; error?: string; expiring?: boolean }) {
  const t = useTranslations("reservations");
  const locale = useLocale();
  const daysRemainingLabel = (days: number) => days < 0 ? t("expiration.past", {days:Math.abs(days)}) : days === 0 ? t("expiration.today") : t("expiration.remaining", {days});
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>{t("table.reservation")}</TableHead><TableHead>{t("table.technologyClass")}</TableHead><TableHead>{t("table.accountRegion")}</TableHead><TableHead numeric>{t("table.quantity")}</TableHead><TableHead numeric>{t("table.utilization")}</TableHead><TableHead>{t("table.expiration")}</TableHead><TableHead>{t("table.status")}</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle={expiring ? t("table.noExpiring") : t("table.noReservations")} emptyDescription={expiring ? t("table.noExpiringDescription") : t("table.noReservationsDescription")} colSpan={7} /> : (
        <TableBody>{items.map((item) => { const expiration = expirationState(item); return <TableRow key={item.reservation_id}><TableCell><ResourceIdentifier primary={item.reservation} copyValue={item.reservation} /></TableCell><TableCell>{item.engine}<span className={styles.secondary}>{item.instance_class}</span></TableCell><TableCell>{item.account.name || item.account.account_id}<span className={styles.secondary}>{item.region}</span></TableCell><TableCell numeric>{item.quantity}</TableCell><TableCell numeric><PercentageDisplay value={item.utilization_percentage} /><span className={styles.secondary}>{formatNu(item.allocated_capacity)} / {formatNu(item.total_capacity)}</span></TableCell><TableCell>{formatDate(item.expiration_at, locale)}<span className={styles.secondary}>{daysRemainingLabel(item.days_remaining)}</span></TableCell><TableCell>{expiring ? <StatusIndicator status={expiration.status} label={expiration.label === "Expired" ? t("expiration.expired") : expiration.label === "Expiring soon" ? t("expiration.expiringSoon") : t("expiration.expiring")} /> : <StatusIndicator status={reservationTone(item.state)} label={item.state.toLowerCase() === "active" ? t("presence.active") : humanize(item.state)} />}</TableCell></TableRow>; })}</TableBody>
      )}
    </Table>
  );
}

function OpportunitiesTable({ page, loading, error }: { page?: RdsPage<RdsReservationOpportunity>; loading: boolean; error?: string }) {
  const t = useTranslations("reservations");
  const opportunityLabels: Record<string,string> = {RDS_RESERVATION_UNCOVERED:t("opportunityTypes.uncovered"),RDS_RESERVATION_PARTIAL_COVERAGE:t("opportunityTypes.partial"),RDS_RESERVATION_UNUSED_CAPACITY:t("opportunityTypes.unused"),RDS_RESERVATION_EXPIRING:t("opportunityTypes.expiring")};
  const severityLabels: Record<string,string> = {high:t("severity.high"),medium:t("severity.medium"),low:t("severity.low")};
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>{t("table.resource")}</TableHead><TableHead>{t("table.opportunity")}</TableHead><TableHead>{t("table.accountRegion")}</TableHead><TableHead>{t("table.recommendation")}</TableHead><TableHead>{t("table.status")}</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle={t("table.noOpportunities")} emptyDescription={t("table.noOpportunitiesDescription")} colSpan={5} /> : (
        <TableBody>{items.map((item) => <TableRow key={item.id}><TableCell><ResourceIdentifier primary={item.resource} technicalId={item.resource_id !== item.resource ? item.resource_id : undefined} /></TableCell><TableCell>{opportunityLabels[item.type] ?? opportunityTypeLabel(item.type)}<span className={styles.secondary}>{item.description}</span></TableCell><TableCell>{item.account_name || item.account_id}<span className={styles.secondary}>{item.region || t("table.regionUnavailable")}</span></TableCell><TableCell>{item.recommended_action || t("table.reviewCoverage")}<span className={styles.secondary}>{t("table.savingsNotCalculated")}</span></TableCell><TableCell><StatusIndicator status={item.severity === "high" ? "danger" : item.severity === "medium" ? "warning" : "neutral"} label={severityLabels[item.severity] ?? humanize(item.severity)} /></TableCell></TableRow>)}</TableBody>
      )}
    </Table>
  );
}

function PageControls({ page, onChange }: { page?: RdsPage<unknown>; onChange: (page: number) => void }) {
  if (!page || page.total_pages <= 1) return null;
  return <div className={styles.pagination}><Pagination page={page.page} pageCount={page.total_pages} onPageChange={onChange} /></div>;
}

function ReservationsContent() {
  const t = useTranslations("reservations");
  const locale = useLocale();
  const tabLabels = useTabLabels();
  const queryError = useQueryError();
  const statusLabels: Record<string,string> = {COMPLETED:t("pipeline.status.completed"),RUNNING:t("pipeline.status.running"),FAILED:t("pipeline.status.failed"),STALE:t("pipeline.status.stale"),COMPLETED_WITH_WARNINGS:t("pipeline.status.completedWithWarnings"),NEVER_EXECUTED:t("pipeline.status.neverExecuted")};
  const freshLabels: Record<string,string> = {FRESH:t("pipeline.fresh.fresh"),STALE:t("pipeline.fresh.stale")};
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const state = useMemo(() => parseRdsReservationSearchParams(searchParams), [searchParams]);
  const update = (changes: Partial<RdsReservationQueryState>) => router.replace(`${pathname}${patchRdsReservationUrl(state, changes)}`, { scroll: false });
  const clear = () => router.replace(pathname, { scroll: false });

  const summaryQuery = buildRdsDashboardQuery(state, "summary");
  const optionsQuery = buildRdsDashboardQuery(state, "options");
  const mainKind = state.tab === "coverage" ? "coverage" : state.tab === "reservations" ? "reservations" : state.tab === "expiring" ? "expiring" : "opportunities";
  const mainQuery = buildRdsDashboardQuery(state, mainKind);

  const operational = useApiQuery<RdsReservationsOperationalStatus>({ key: ["rds-reservations", "operational-status"], path: "/rds/reservations/operational-status", ...cachePolicy.operational });
  const summary = useApiQuery<RdsReservationsSummary>({ key: ["rds-reservations", "summary", summaryQuery], path: `/rds/reservations-dashboard/summary${summaryQuery ? `?${summaryQuery}` : ""}`, ...cachePolicy.operational });
  const options = useApiQuery<RdsReservationsOptions>({ key: ["rds-reservations", "options", optionsQuery], path: `/rds/reservations-dashboard/options${optionsQuery ? `?${optionsQuery}` : ""}`, ...cachePolicy.metadata });
  const coverage = useApiQuery<RdsPage<RdsCoverageItem>>({ key: ["rds-reservations", "coverage", mainQuery], path: `/rds/reservations-dashboard/coverage?${mainQuery}`, enabled: state.tab === "coverage", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });
  const reservations = useApiQuery<RdsPage<RdsReservationUtilization>>({ key: ["rds-reservations", state.tab, mainQuery], path: `/rds/reservations-dashboard/reservations?${mainQuery}`, enabled: state.tab === "reservations" || state.tab === "expiring", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });
  const opportunities = useApiQuery<RdsPage<RdsReservationOpportunity>>({ key: ["rds-reservations", "opportunities", mainQuery], path: `/rds/reservations-dashboard/opportunities?${mainQuery}`, enabled: state.tab === "opportunities", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });
  const main = state.tab === "coverage" ? coverage : state.tab === "opportunities" ? opportunities : reservations;
  const mainError = main.error ? queryError(main.error, t("errors.loadData")) : undefined;
  const coverageNotReady = summary.error instanceof ApiError && summary.error.status === 404 && operational.data && ["NEVER_EXECUTED", "RUNNING", "FAILED"].includes(operational.data.pipeline_status);

  const refresh = () => { void operational.refetch(); void summary.refetch(); void options.refetch(); void main.refetch(); };
  const metrics: Array<{ label: string; value: ReactNode; supportingText: string; icon: ReactNode }> = [
    { label: t("metrics.active"), value: summary.data?.reservations.active ?? "—", supportingText: t("metrics.activeDescription"), icon: <Cloud {...iconDefaults} /> },
    { label: t("metrics.coverage"), value: <PercentageDisplay value={summary.data?.coverage.coverage_percentage} />, supportingText: t("metrics.covered", {covered:formatNu(summary.data?.coverage.covered_units ?? 0),required:formatNu(summary.data?.coverage.required_units ?? 0)}), icon: <ShieldCheck {...iconDefaults} /> },
    { label: t("metrics.utilization"), value: <PercentageDisplay value={summary.data?.reservations.utilization_percentage} />, supportingText: t("metrics.allocated", {allocated:formatNu(summary.data?.reservations.used_units ?? 0),reserved:formatNu(summary.data?.reservations.reserved_units ?? 0)}), icon: <Gauge {...iconDefaults} /> },
    { label: t("metrics.expiring"), value: summary.data?.expiring_next_30_days ?? "—", supportingText: t("metrics.expiringDescription"), icon: <TimerReset {...iconDefaults} /> },
    { label: t("metrics.uncovered"), value: summary.data?.rds.uncovered ?? "—", supportingText: t("metrics.unknown", {count:summary.data?.rds.unknown ?? 0}), icon: <AlertTriangle {...iconDefaults} /> },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title={t("title")} description={t("description")} metadata={<ProviderBadge provider="aws" />} actions={<Button variant="outline" leadingIcon={<RefreshCw {...iconDefaults} />} loading={operational.isFetching || summary.isFetching || main.isFetching} onClick={refresh}>{t("actions.refresh")}</Button>} />

      <OperationalNotice status={operational.data} />
      {operational.error && <Alert variant="warning" title={t("states.operationalUnavailable")} description={queryError(operational.error, t("errors.loadPipeline"))} />}
      {summary.error && !coverageNotReady && <Alert variant={summary.error instanceof ApiError && summary.error.status === 404 ? "warning" : "danger"} title={t("states.summaryUnavailable")} description={queryError(summary.error, t("errors.loadSummary"))} />}
      {options.error && <Alert variant="warning" title={t("states.optionsUnavailable")} description={queryError(options.error, t("errors.loadOptions"))} />}

      {operational.data && (
        <Section appearance="card" title={t("pipeline.sectionTitle")} description={t("pipeline.sectionDescription")}>
          <div className={styles.capacityGrid}>
            <div><span>{t("pipeline.label")}</span><StatusIndicator status={operationalTone(operational.data.pipeline_status)} label={statusLabels[operational.data.pipeline_status] ?? humanize(operational.data.pipeline_status)} /></div>
            <div><span>{t("pipeline.freshness")}</span><StatusIndicator status={operational.data.data_freshness === "FRESH" ? "success" : operational.data.data_freshness === "STALE" ? "warning" : "neutral"} label={freshLabels[operational.data.data_freshness] ?? humanize(operational.data.data_freshness)} /></div>
            <div><span>{t("pipeline.lastCollection")}</span><strong>{formatDateTime(operational.data.last_inventory_collection_at, locale)}</strong></div>
            <div><span>{t("pipeline.lastCoverage")}</span><strong>{formatDateTime(operational.data.last_successful_coverage_run_at, locale)}</strong></div>
          </div>
        </Section>
      )}

      <Filters state={state} options={options.data} loading={options.isLoading} onChange={update} onClear={clear} />

      <Section title={t("overview.title")} description={t("overview.description")}>
        <div className={styles.metricsGrid} aria-label={t("overview.aria")}>{metrics.map((metric) => <MetricCard key={metric.label} {...metric} loading={summary.isLoading} />)}</div>
      </Section>

      <Section title={t("analysis.title")} description={t("analysis.description")}>
        <div className={styles.analysisGrid}><CoverageSummary summary={summary.data} loading={summary.isLoading} /><CapacitySummary summary={summary.data} loading={summary.isLoading} /></div>
      </Section>

      <Section title={t("explorer.title")} description={t("explorer.description")}>
        <Tabs value={state.tab} defaultValue="coverage" onValueChange={(value) => update({ tab: value as RdsReservationQueryState["tab"], page: 1, sort: "", order: value === "opportunities" ? "desc" : "asc" })}>
          <TabsList aria-label={t("explorer.aria")}>{(Object.entries(tabLabels) as Array<[RdsReservationQueryState["tab"], string]>).map(([value, label]) => <TabsTrigger key={value} value={value}>{label}</TabsTrigger>)}</TabsList>
          <div className={styles.tableHeading}><div><h3>{tabLabels[state.tab]}</h3><p>{state.tab === "expiring" ? t("explorer.expiringDescription") : t("explorer.defaultDescription")}</p></div>{main.isFetching && !main.isLoading ? <StatusIndicator status="pending" label={t("states.updating")} /> : null}</div>
          <TabsContent value="coverage"><CoverageTable page={coverage.data} loading={coverage.isLoading} error={mainError} /></TabsContent>
          <TabsContent value="reservations"><ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} /></TabsContent>
          <TabsContent value="expiring"><ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} expiring /></TabsContent>
          <TabsContent value="opportunities"><OpportunitiesTable page={opportunities.data} loading={opportunities.isLoading} error={mainError} /></TabsContent>
          <PageControls page={main.data as RdsPage<unknown> | undefined} onChange={(page) => update({ page })} />
        </Tabs>
      </Section>

      <Alert variant="info" title={t("scope.title")} description={t("scope.description")} />
    </div>
  );
}

export default function RdsReservationsPage() {
  return <Suspense fallback={<div className={styles.page}><Skeleton /><Skeleton /><Skeleton /></div>}><ReservationsContent /></Suspense>;
}
