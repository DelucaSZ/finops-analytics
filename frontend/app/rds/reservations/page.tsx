"use client";

import { Suspense, useMemo, type ReactNode } from "react";
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

const TAB_LABELS: Record<RdsReservationQueryState["tab"], string> = {
  coverage: "Coverage",
  reservations: "Active reservations",
  expiring: "Expiring reservations",
  opportunities: "Reservation opportunities",
};

const EXPIRATION_LABELS: Record<string, string> = {
  LE_7: "≤7 days",
  LE_15: "≤15 days",
  LE_30: "≤30 days",
  GT_30: ">30 days",
  EXPIRED: "Expired",
};

function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(date);
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
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

function queryError(error: unknown, fallback: string) {
  if (!(error instanceof ApiError)) return fallback;
  if (error.code === "RDS_COVERAGE_NOT_CALCULATED" || error.status === 404) return "RDS reservation coverage has not been calculated yet.";
  if (error.status === 403) return "You do not have permission to view RDS reservation data.";
  if (error.status === 429) return "Reservation data is temporarily rate limited. Try again shortly.";
  if (error.status === 400) return "The reservation request was rejected for the current scope or filters.";
  if (error.status === 502 || error.status === 503) return "The reservation provider API is temporarily unavailable.";
  return fallback;
}

function operationalTone(status?: RdsReservationsOperationalStatus["pipeline_status"]) {
  if (status === "COMPLETED") return "success" as const;
  if (status === "RUNNING") return "pending" as const;
  if (status === "FAILED") return "danger" as const;
  if (status === "STALE" || status === "COMPLETED_WITH_WARNINGS") return "warning" as const;
  return "neutral" as const;
}

function OperationalNotice({ status }: { status?: RdsReservationsOperationalStatus }) {
  if (!status) return null;
  if (status.pipeline_status === "NEVER_EXECUTED") {
    return <Alert variant="warning" title="Reservation data has not been processed yet" description="The RDS Reservations pipeline has not completed its first inventory and coverage run. The worker will bootstrap it automatically for configured AWS accounts." />;
  }
  if (status.pipeline_status === "RUNNING") {
    return <Alert variant="info" title="Reservation data is updating" description={`The RDS Reservations pipeline is currently running${status.pipeline_stage ? ` (${humanize(status.pipeline_stage)})` : ""}. Existing completed coverage remains available while the refresh finishes.`} />;
  }
  if (status.pipeline_status === "FAILED") {
    return <Alert variant="danger" title="Last reservation refresh failed" description={status.coverage_run_id ? "The latest pipeline attempt failed. The last successful coverage snapshot remains available below." : "The latest pipeline attempt failed before a valid coverage snapshot was produced."} />;
  }
  if (status.pipeline_status === "STALE") {
    return <Alert variant="warning" title="Data may be outdated" description={`The latest valid RDS inventory is older than the configured ${status.freshness_threshold_hours}-hour freshness threshold. The worker will refresh it automatically.`} />;
  }
  if (status.pipeline_status === "COMPLETED_WITH_WARNINGS") {
    return <Alert variant="warning" title="Coverage updated with an opportunity-processing warning" description="The coverage snapshot is valid, but opportunity generation did not complete. It can be retried without invalidating coverage." />;
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

function daysRemainingLabel(days: number) {
  if (days < 0) return `${Math.abs(days)} days past expiration`;
  if (days === 0) return "Expires today";
  return `${days} days remaining`;
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
    return <TableBody><TableRow staticRow><TableCell colSpan={colSpan}><Alert variant="danger" title="Unable to load reservation data" description={error} /></TableCell></TableRow></TableBody>;
  }
  if (empty) {
    return <TableBody><TableRow staticRow><TableCell colSpan={colSpan}><DataState empty emptyTitle={emptyTitle} emptyDescription={emptyDescription}><span /></DataState></TableCell></TableRow></TableBody>;
  }
  return null;
}

function CoverageSummary({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const total = summary?.rds.total ?? 0;
  const groups = [
    ["Full", summary?.rds.fully_covered ?? 0, styles.full],
    ["Partial", summary?.rds.partially_covered ?? 0, styles.partial],
    ["Uncovered", summary?.rds.uncovered ?? 0, styles.uncovered],
    ["Unknown", summary?.rds.unknown ?? 0, styles.unknown],
  ] as const;
  return (
    <ChartCard title="Coverage distribution" description="Current RDS workloads by backend coverage status." loading={loading} empty={!loading && total === 0} emptyTitle="No RDS workloads in scope" emptyDescription="No eligible workloads are available for the current filters." legend={(
      <div className={styles.legend}>{groups.map(([label, value, tone]) => <span className={styles.legendItem} key={label}><span className={`${styles.dot} ${tone}`} aria-hidden="true" />{label}<strong>{value}</strong></span>)}</div>
    )}>
      <div className={styles.distribution} role="img" aria-label={`Coverage distribution: ${groups.map(([label, value]) => `${label} ${value}`).join(", ")}`}>
        {groups.map(([label, value, tone]) => value > 0 ? <span key={label} className={`${styles.segment} ${tone}`} style={{ inlineSize: `${(value / total) * 100}%` }} title={`${label}: ${value}`} /> : null)}
      </div>
    </ChartCard>
  );
}

function CapacitySummary({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  return (
    <Section appearance="card" title="Reserved capacity" description="Utilization is allocated reserved capacity, distinct from workload coverage.">
      <DataState loading={loading}>
        <div className={styles.capacityGrid}>
          <div className={styles.capacityPrimary}><span>Utilization</span><strong><PercentageDisplay value={summary?.reservations.utilization_percentage} /></strong><small>{formatNu(summary?.reservations.used_units ?? 0)} / {formatNu(summary?.reservations.reserved_units ?? 0)}</small></div>
          <div><span>Reserved</span><strong>{formatNu(summary?.reservations.reserved_units ?? 0)}</strong></div>
          <div><span>Allocated</span><strong>{formatNu(summary?.reservations.used_units ?? 0)}</strong></div>
          <div><span>Unused</span><strong>{formatNu(summary?.reservations.unused_units ?? 0)}</strong></div>
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
  return (
    <FilterBar aria-label="Context and filters" actions={<Button variant="ghost" size="sm" onClick={onClear}>Clear filters</Button>}>
      <AccountSelector label="Account" value={state.account} onChange={(account) => onChange({ account, page: 1 })} options={accountOptions(options)} loading={loading} placeholder="All authorized accounts" clearLabel="All authorized accounts" />
      <Select label="Region" value={state.region} onChange={(event) => onChange({ region: event.target.value, page: 1 })} options={selectOptions(options?.regions)} placeholder="All regions" />
      <Select label="Engine" value={state.engine} onChange={(event) => onChange({ engine: event.target.value, page: 1 })} options={selectOptions(options?.engines)} placeholder="All engines" />
      <Select label="Family" value={state.family} onChange={(event) => onChange({ family: event.target.value, page: 1 })} options={selectOptions(options?.families)} placeholder="All families" />
      <Select label="Class" value={state.instanceClass} onChange={(event) => onChange({ instanceClass: event.target.value, page: 1 })} options={selectOptions(options?.instance_classes)} placeholder="All classes" />
      {state.tab === "coverage" && <Select label="Coverage" value={state.coverageStatus} onChange={(event) => onChange({ coverageStatus: event.target.value, page: 1 })} options={["FULL", "PARTIAL", "UNCOVERED", "UNKNOWN"].map((value) => ({ value, label: coverageStatusLabel(value) }))} placeholder="All statuses" />}
      {(state.tab === "reservations" || state.tab === "expiring") && <Select label="Expiration" value={state.expirationRange} onChange={(event) => onChange({ expirationRange: event.target.value, page: 1 })} options={Object.entries(EXPIRATION_LABELS).map(([value, label]) => ({ value, label }))} placeholder={state.tab === "expiring" ? "≤30 days" : "All expirations"} />}
      {state.tab === "opportunities" && <Select label="Opportunity" value={state.opportunityType} onChange={(event) => onChange({ opportunityType: event.target.value, page: 1 })} options={["RDS_RESERVATION_UNCOVERED", "RDS_RESERVATION_PARTIAL_COVERAGE", "RDS_RESERVATION_UNUSED_CAPACITY", "RDS_RESERVATION_EXPIRING"].map((value) => ({ value, label: opportunityTypeLabel(value) }))} placeholder="All opportunity types" />}
    </FilterBar>
  );
}

function CoverageTable({ page, loading, error }: { page?: RdsPage<RdsCoverageItem>; loading: boolean; error?: string }) {
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>Resource</TableHead><TableHead>Technology</TableHead><TableHead>Account / region</TableHead><TableHead numeric>Coverage</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle="No reservation coverage found" emptyDescription="No eligible RDS workloads match the current filters." colSpan={5} /> : (
        <TableBody>{items.map((item) => <TableRow key={item.instance_id}><TableCell><ResourceIdentifier primary={item.instance} copyValue={item.instance} /><span className={styles.secondary}>{item.instance_class}</span></TableCell><TableCell>{item.engine}<span className={styles.secondary}>{item.engine_version || "Version unavailable"}</span></TableCell><TableCell>{item.account.name || item.account.account_id}<span className={styles.secondary}>{item.region}</span></TableCell><TableCell numeric><PercentageDisplay value={item.coverage_percentage} /><span className={styles.secondary}>{formatNu(item.covered_units)} / {formatNu(item.required_units)}</span></TableCell><TableCell><StatusIndicator status={coverageTone(item.coverage_status)} label={coverageStatusLabel(item.coverage_status)} /></TableCell></TableRow>)}</TableBody>
      )}
    </Table>
  );
}

function ReservationsTable({ page, loading, error, expiring = false }: { page?: RdsPage<RdsReservationUtilization>; loading: boolean; error?: string; expiring?: boolean }) {
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>Reservation</TableHead><TableHead>Technology / class</TableHead><TableHead>Account / region</TableHead><TableHead numeric>Quantity</TableHead><TableHead numeric>Utilization</TableHead><TableHead>Expiration</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle={expiring ? "No reservations expire in the selected window" : "No active reservations found"} emptyDescription={expiring ? "No reservation matches the current expiration window and filters." : "No active Reserved DB Instances match the current filters."} colSpan={7} /> : (
        <TableBody>{items.map((item) => { const expiration = expirationState(item); return <TableRow key={item.reservation_id}><TableCell><ResourceIdentifier primary={item.reservation} copyValue={item.reservation} /></TableCell><TableCell>{item.engine}<span className={styles.secondary}>{item.instance_class}</span></TableCell><TableCell>{item.account.name || item.account.account_id}<span className={styles.secondary}>{item.region}</span></TableCell><TableCell numeric>{item.quantity}</TableCell><TableCell numeric><PercentageDisplay value={item.utilization_percentage} /><span className={styles.secondary}>{formatNu(item.allocated_capacity)} / {formatNu(item.total_capacity)}</span></TableCell><TableCell>{formatDate(item.expiration_at)}<span className={styles.secondary}>{daysRemainingLabel(item.days_remaining)}</span></TableCell><TableCell>{expiring ? <StatusIndicator status={expiration.status} label={expiration.label} /> : <StatusIndicator status={reservationTone(item.state)} label={humanize(item.state)} />}</TableCell></TableRow>; })}</TableBody>
      )}
    </Table>
  );
}

function OpportunitiesTable({ page, loading, error }: { page?: RdsPage<RdsReservationOpportunity>; loading: boolean; error?: string }) {
  const items = page?.items ?? [];
  const hasState = loading || Boolean(error) || items.length === 0;
  return (
    <Table>
      <TableHeader><TableRow staticRow><TableHead>Resource</TableHead><TableHead>Opportunity</TableHead><TableHead>Account / region</TableHead><TableHead>Recommendation</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
      {hasState ? <TableState loading={loading} error={error} empty={!loading && !error && items.length === 0} emptyTitle="No reservation opportunities identified" emptyDescription="No active RDS reservation opportunity matches the current filters." colSpan={5} /> : (
        <TableBody>{items.map((item) => <TableRow key={item.id}><TableCell><ResourceIdentifier primary={item.resource} technicalId={item.resource_id !== item.resource ? item.resource_id : undefined} /></TableCell><TableCell>{opportunityTypeLabel(item.type)}<span className={styles.secondary}>{item.description}</span></TableCell><TableCell>{item.account_name || item.account_id}<span className={styles.secondary}>{item.region || "Region unavailable"}</span></TableCell><TableCell>{item.recommended_action || "Review the coverage context before taking action."}<span className={styles.secondary}>Potential savings are not calculated by this contract.</span></TableCell><TableCell><StatusIndicator status={item.severity === "high" ? "danger" : item.severity === "medium" ? "warning" : "neutral"} label={humanize(item.severity)} /></TableCell></TableRow>)}</TableBody>
      )}
    </Table>
  );
}

function PageControls({ page, onChange }: { page?: RdsPage<unknown>; onChange: (page: number) => void }) {
  if (!page || page.total_pages <= 1) return null;
  return <div className={styles.pagination}><Pagination page={page.page} pageCount={page.total_pages} onPageChange={onChange} /></div>;
}

function ReservationsContent() {
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
  const mainError = main.error ? queryError(main.error, "Could not load RDS reservation data.") : undefined;
  const coverageNotReady = summary.error instanceof ApiError && summary.error.status === 404 && operational.data && ["NEVER_EXECUTED", "RUNNING", "FAILED"].includes(operational.data.pipeline_status);

  const refresh = () => { void operational.refetch(); void summary.refetch(); void options.refetch(); void main.refetch(); };
  const metrics: Array<{ label: string; value: ReactNode; supportingText: string; icon: ReactNode }> = [
    { label: "Active reservations", value: summary.data?.reservations.active ?? "—", supportingText: "Reserved DB Instances currently active", icon: <Cloud {...iconDefaults} /> },
    { label: "Reservation coverage", value: <PercentageDisplay value={summary.data?.coverage.coverage_percentage} />, supportingText: `${formatNu(summary.data?.coverage.covered_units ?? 0)} / ${formatNu(summary.data?.coverage.required_units ?? 0)} covered`, icon: <ShieldCheck {...iconDefaults} /> },
    { label: "Utilization", value: <PercentageDisplay value={summary.data?.reservations.utilization_percentage} />, supportingText: `${formatNu(summary.data?.reservations.used_units ?? 0)} / ${formatNu(summary.data?.reservations.reserved_units ?? 0)} allocated`, icon: <Gauge {...iconDefaults} /> },
    { label: "Expiring within 30 days", value: summary.data?.expiring_next_30_days ?? "—", supportingText: "Backend-classified active reservations", icon: <TimerReset {...iconDefaults} /> },
    { label: "Uncovered RDS", value: summary.data?.rds.uncovered ?? "—", supportingText: `${summary.data?.rds.unknown ?? 0} unable to determine`, icon: <AlertTriangle {...iconDefaults} /> },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title="RDS Reservations" description="Analyze reservation coverage, reserved-capacity utilization, expirations and RDS reservation opportunities." metadata={<ProviderBadge provider="aws" />} actions={<Button variant="outline" leadingIcon={<RefreshCw {...iconDefaults} />} loading={operational.isFetching || summary.isFetching || main.isFetching} onClick={refresh}>Refresh</Button>} />

      <OperationalNotice status={operational.data} />
      {operational.error && <Alert variant="warning" title="Operational status unavailable" description={queryError(operational.error, "Could not load the RDS Reservations pipeline status.")} />}
      {summary.error && !coverageNotReady && <Alert variant={summary.error instanceof ApiError && summary.error.status === 404 ? "warning" : "danger"} title="Reservation summary unavailable" description={queryError(summary.error, "Could not load the reservation summary.")} />}
      {options.error && <Alert variant="warning" title="Some filter options are unavailable" description={queryError(options.error, "Could not load reservation filter options.")} />}

      {operational.data && (
        <Section appearance="card" title="Data status" description="Operational state is calculated by the backend; analytical views continue using the latest successful coverage snapshot.">
          <div className={styles.capacityGrid}>
            <div><span>Pipeline</span><StatusIndicator status={operationalTone(operational.data.pipeline_status)} label={humanize(operational.data.pipeline_status)} /></div>
            <div><span>Data freshness</span><StatusIndicator status={operational.data.data_freshness === "FRESH" ? "success" : operational.data.data_freshness === "STALE" ? "warning" : "neutral"} label={humanize(operational.data.data_freshness)} /></div>
            <div><span>Last AWS collection</span><strong>{formatDateTime(operational.data.last_inventory_collection_at)}</strong></div>
            <div><span>Last coverage calculation</span><strong>{formatDateTime(operational.data.last_successful_coverage_run_at)}</strong></div>
          </div>
        </Section>
      )}

      <Filters state={state} options={options.data} loading={options.isLoading} onChange={update} onClear={clear} />

      <Section title="Reservation overview" description="Current operational state for the selected AWS reservation scope.">
        <div className={styles.metricsGrid} aria-label="RDS reservation summary">{metrics.map((metric) => <MetricCard key={metric.label} {...metric} loading={summary.isLoading} />)}</div>
      </Section>

      <Section title="Coverage and utilization" description="Coverage measures eligible workload capacity protected by compatible reservations. Utilization measures how much reserved capacity is allocated.">
        <div className={styles.analysisGrid}><CoverageSummary summary={summary.data} loading={summary.isLoading} /><CapacitySummary summary={summary.data} loading={summary.isLoading} /></div>
      </Section>

      <Section title="Reservation explorer" description="Operational tables preserve the current API and matching contracts.">
        <Tabs value={state.tab} defaultValue="coverage" onValueChange={(value) => update({ tab: value as RdsReservationQueryState["tab"], page: 1, sort: "", order: value === "opportunities" ? "desc" : "asc" })}>
          <TabsList aria-label="RDS reservation views">{(Object.entries(TAB_LABELS) as Array<[RdsReservationQueryState["tab"], string]>).map(([value, label]) => <TabsTrigger key={value} value={value}>{label}</TabsTrigger>)}</TabsList>
          <div className={styles.tableHeading}><div><h3>{TAB_LABELS[state.tab]}</h3><p>{state.tab === "expiring" ? "Default window: reservations expiring within 30 days. Expired remains a distinct state." : "Data is produced by the existing reservation coverage and opportunity services."}</p></div>{main.isFetching && !main.isLoading ? <StatusIndicator status="pending" label="Updating" /> : null}</div>
          <TabsContent value="coverage"><CoverageTable page={coverage.data} loading={coverage.isLoading} error={mainError} /></TabsContent>
          <TabsContent value="reservations"><ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} /></TabsContent>
          <TabsContent value="expiring"><ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} expiring /></TabsContent>
          <TabsContent value="opportunities"><OpportunitiesTable page={opportunities.data} loading={opportunities.isLoading} error={mainError} /></TabsContent>
          <PageControls page={main.data as RdsPage<unknown> | undefined} onChange={(page) => update({ page })} />
        </Tabs>
      </Section>

      <Alert variant="info" title="Recommendation scope" description="This view identifies reservation coverage and opportunities. It does not calculate acquisition savings, invent currency, execute Reserved DB Instance purchases, or recalculate reservation matching in the UI." />
    </div>
  );
}

export default function RdsReservationsPage() {
  return <Suspense fallback={<div className={styles.page}><Skeleton /><Skeleton /><Skeleton /></div>}><ReservationsContent /></Suspense>;
}
