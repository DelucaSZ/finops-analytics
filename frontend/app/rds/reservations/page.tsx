"use client";

import { Fragment, Suspense, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  AlertTriangle,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  CircleHelp,
  Cloud,
  Database,
  Gauge,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  TimerReset,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/lib/api";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import type {
  RdsCoverageItem,
  RdsPage,
  RdsReservationOpportunity,
  RdsReservationsOptions,
  RdsReservationsSummary,
  RdsReservationUtilization,
} from "@/lib/rds-reservations";
import {
  buildRdsDashboardQuery,
  clampPercentage,
  coverageStatusLabel,
  formatNu,
  opportunityTypeLabel,
  parseRdsReservationSearchParams,
  patchRdsReservationUrl,
} from "@/lib/rds-reservations-query.mjs";
import type { RdsReservationQueryState } from "@/lib/rds-reservations-query.mjs";
import styles from "./rds-reservations.module.css";

const tabLabels = {
  coverage: "Coverage",
  reservations: "Reservations",
  expiring: "Expiring",
  opportunities: "Opportunities",
} as const;

const coverageTone: Record<string, string> = {
  FULL: styles.positive,
  PARTIAL: styles.warning,
  UNCOVERED: styles.critical,
  UNKNOWN: styles.neutral,
};

const severityLabels: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const expirationLabels: Record<string, string> = {
  LE_7: "≤7 days",
  LE_15: "≤15 days",
  LE_30: "≤30 days",
  GT_30: ">30 days",
  EXPIRED: "Expired",
};

function accountLabel(account: { name: string | null; account_id: string }) {
  return account.name ? `${account.name} · ${account.account_id}` : account.account_id;
}

function formatPercent(value: number) {
  return `${Number(value || 0).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function relativeTime(value: string | null | undefined) {
  if (!value) return "Unavailable";
  const ms = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(ms)) return "Unavailable";
  const minutes = Math.max(0, Math.round(ms / 60_000));
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} d ago`;
}

function humanize(value: string | null | undefined) {
  if (!value) return "—";
  return value
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function unknownReason(explanation: Record<string, unknown>) {
  const reason = explanation.reason ?? explanation.code ?? explanation.status_reason;
  if (typeof reason === "string") return humanize(reason);
  return "The backend could not determine reservation coverage for this workload.";
}

function queryError(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    if (error.code === "RDS_COVERAGE_NOT_CALCULATED" || error.status === 404) {
      return "RDS reservation coverage has not been calculated yet.";
    }
    if (error.status === 403) return "You do not have permission to view RDS reservation data.";
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

function Badge({ children, tone = styles.neutral }: { children: React.ReactNode; tone?: string }) {
  return <span className={`${styles.badge} ${tone}`}>{children}</span>;
}

function TooltipLabel({ label, help }: { label: string; help: string }) {
  return (
    <span className={styles.tooltipLabel} title={help} aria-label={`${label}. ${help}`}>
      {label}<CircleHelp size={13} aria-hidden="true" />
    </span>
  );
}

function Progress({ value, tone = "positive" }: { value: number; tone?: "positive" | "warning" | "critical" | "neutral" }) {
  const safe = clampPercentage(value);
  return (
    <div className={styles.progress} aria-label={`${safe}%`}>
      <span className={`${styles.progressFill} ${styles[`progress${tone.charAt(0).toUpperCase()}${tone.slice(1)}`]}`} style={{ width: `${safe}%` }} />
    </div>
  );
}

function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`${styles.skeleton} ${className}`} aria-hidden="true" />;
}

function MetricCard({ label, value, detail, loading, icon }: {
  label: string;
  value: string | number;
  detail?: string;
  loading?: boolean;
  icon: React.ReactNode;
}) {
  return (
    <article className={styles.metricCard}>
      <div className={styles.metricIcon}>{icon}</div>
      <span>{label}</span>
      {loading ? <Skeleton className={styles.metricSkeleton} /> : <strong>{value}</strong>}
      {loading ? <Skeleton className={styles.detailSkeleton} /> : <small>{detail || "\u00a0"}</small>}
    </article>
  );
}

function StatusDistribution({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const total = summary?.rds.total || 0;
  const groups = [
    ["Full", summary?.rds.fully_covered || 0, styles.segmentFull],
    ["Partial", summary?.rds.partially_covered || 0, styles.segmentPartial],
    ["Uncovered", summary?.rds.uncovered || 0, styles.segmentUncovered],
    ["Unknown", summary?.rds.unknown || 0, styles.segmentUnknown],
  ] as const;
  return (
    <section className={styles.panel} aria-labelledby="coverage-overview-title">
      <div className={styles.panelHeading}><div><span className={styles.kicker}>WORKLOAD DISTRIBUTION</span><h2 id="coverage-overview-title">Coverage Overview</h2></div></div>
      <div className={styles.chartBody}>
        {loading ? <Skeleton className={styles.chartSkeleton} /> : total === 0 ? <div className={styles.inlineEmpty}>No RDS workloads in scope.</div> : <>
          <div className={styles.stackedBar} aria-label="Coverage status distribution">
            {groups.map(([label, value, className]) => value > 0 && <span key={label} className={className} style={{ width: `${(value / total) * 100}%` }} title={`${label}: ${value}`} />)}
          </div>
          <div className={styles.legendGrid}>{groups.map(([label, value, className]) => <div key={label}><span className={`${styles.legendDot} ${className}`} /><span>{label}</span><strong>{value}</strong></div>)}</div>
        </>}
      </div>
    </section>
  );
}

function CapacityOverview({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const reserved = summary?.reservations.reserved_units || 0;
  const used = summary?.reservations.used_units || 0;
  const unused = summary?.reservations.unused_units || 0;
  const utilization = summary?.reservations.utilization_percentage || 0;
  return (
    <section className={styles.panel} aria-labelledby="capacity-overview-title">
      <div className={styles.panelHeading}><div><span className={styles.kicker}>RESERVATION UTILIZATION</span><h2 id="capacity-overview-title">Reserved Capacity</h2></div><TooltipLabel label="Utilization" help="Reservation utilization measures allocated reserved capacity. It is different from workload coverage." /></div>
      <div className={styles.capacityBody}>
        {loading ? <Skeleton className={styles.chartSkeleton} /> : <>
          <div className={styles.capacityHeadline}><strong>{formatNu(reserved)}</strong><span>total reserved capacity</span></div>
          <Progress value={utilization} tone={unused > 0 ? "warning" : "positive"} />
          <div className={styles.capacityStats}><div><span>Used</span><strong>{formatNu(used)}</strong></div><div><span>Unused</span><strong>{formatNu(unused)}</strong></div><div><span>Utilization</span><strong>{formatPercent(utilization)}</strong></div></div>
        </>}
      </div>
    </section>
  );
}

function BillingCoverage({ summary, loading }: { summary?: RdsReservationsSummary; loading: boolean }) {
  const observed = summary?.billing.aws_observed_coverage_percentage;
  const validationAvailable = summary?.billing.validation_status === "AVAILABLE" && observed !== null && observed !== undefined;
  return (
    <section className={styles.billingPanel} aria-label="Technical and AWS observed coverage">
      <div><span>Current Technical Coverage</span>{loading ? <Skeleton className={styles.inlineSkeleton} /> : <strong>{formatPercent(summary?.billing.technical_coverage_percentage || 0)}</strong>}<small>Current inventory + active reservations</small></div>
      <div><TooltipLabel label="AWS Observed Coverage" help="Historical reservation coverage reported by AWS Cost Explorer for a completed billing period." />{loading ? <Skeleton className={styles.inlineSkeleton} /> : validationAvailable ? <strong>{formatPercent(observed || 0)}</strong> : <strong className={styles.unavailable}>Unavailable</strong>}<small>{validationAvailable ? summary?.freshness.billing_data_reference || "Last complete billing period" : "Technical coverage remains available"}</small></div>
      <div><span>AWS Billing Reconciliation</span>{loading ? <Skeleton className={styles.inlineSkeleton} /> : <Badge tone={summary?.billing.reconciliation_status === "MATCH" ? styles.positive : summary?.billing.reconciliation_status === "MISMATCH" ? styles.warning : styles.neutral}>{humanize(summary?.billing.reconciliation_status)}</Badge>}<small>{summary?.billing.reconciliation_detail || "No Cost Explorer reconciliation result available."}</small></div>
    </section>
  );
}

function Filters({ state, options, onChange, onClear }: { state: RdsReservationQueryState; options?: RdsReservationsOptions; onChange: (changes: Partial<RdsReservationQueryState>) => void; onClear: () => void }) {
  return (
    <section className={styles.filters} aria-label="RDS reservation filters">
      <div className={styles.filterHeading}><div><span className={styles.kicker}>FILTERS</span><strong>Scope the analysis</strong></div><button type="button" className="button ghost small" onClick={onClear}><RotateCcw size={14} />Clear</button></div>
      <div className={styles.filterGrid}>
        <label><span>Provider</span><select value="aws" disabled aria-label="Provider"><option value="aws">AWS</option></select></label>
        <label><span>Account</span><select value={state.account} onChange={(event) => onChange({ account: event.target.value, page: 1 })}>
          <option value="">All authorized accounts</option>{(options?.accounts || []).map((account) => <option key={account.account_id} value={account.account_id}>{accountLabel(account)}</option>)}
        </select></label>
        <label><span>Region</span><select value={state.region} onChange={(event) => onChange({ region: event.target.value, page: 1 })}>
          <option value="">All regions</option>{(options?.regions || []).map((value) => <option key={value}>{value}</option>)}
        </select></label>
        <label><span>Engine</span><select value={state.engine} onChange={(event) => onChange({ engine: event.target.value, page: 1 })}>
          <option value="">All engines</option>{(options?.engines || []).map((value) => <option key={value}>{value}</option>)}
        </select></label>
        <label><span>Instance family</span><select value={state.family} onChange={(event) => onChange({ family: event.target.value, page: 1 })}>
          <option value="">All families</option>{(options?.families || []).map((value) => <option key={value}>{value}</option>)}
        </select></label>
        <label><span>Instance class</span><select value={state.instanceClass} onChange={(event) => onChange({ instanceClass: event.target.value, page: 1 })}>
          <option value="">All classes</option>{(options?.instance_classes || []).map((value) => <option key={value}>{value}</option>)}
        </select></label>
        <label><span>Coverage status</span><select value={state.coverageStatus} onChange={(event) => onChange({ coverageStatus: event.target.value, page: 1 })}>
          <option value="">All</option><option value="FULL">Full</option><option value="PARTIAL">Partial</option><option value="UNCOVERED">Uncovered</option><option value="UNKNOWN">Unknown</option>
        </select></label>
        <label><span>Reservation status</span><select value={state.reservationStatus} onChange={(event) => onChange({ reservationStatus: event.target.value, page: 1 })}>
          <option value="">All</option><option value="active">Active</option><option value="retired">Retired</option><option value="payment-pending">Payment pending</option>
        </select></label>
        <label><span>Expiration</span><select value={state.expirationRange} onChange={(event) => onChange({ expirationRange: event.target.value, page: 1 })}>
          <option value="">All</option>{Object.entries(expirationLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label><span>Opportunity type</span><select value={state.opportunityType} onChange={(event) => onChange({ opportunityType: event.target.value, page: 1 })}>
          <option value="">All</option>
          <option value="RDS_RESERVATION_UNCOVERED">Uncovered</option>
          <option value="RDS_RESERVATION_PARTIAL_COVERAGE">Partial coverage</option>
          <option value="RDS_RESERVATION_UNUSED_CAPACITY">Unused capacity</option>
          <option value="RDS_RESERVATION_EXPIRING">Expiring</option>
        </select></label>
      </div>
    </section>
  );
}

function SortControls({ state, onChange }: { state: RdsReservationQueryState; onChange: (changes: Partial<RdsReservationQueryState>) => void }) {
  if (state.tab === "expiring") {
    return <span className={styles.fixedSort}>Expiration ↑</span>;
  }
  const options = state.tab === "coverage"
    ? [["account", "Account"], ["region", "Region"], ["instance", "DB Instance"], ["coverage", "Coverage"], ["required", "Required capacity"]]
    : state.tab === "reservations"
      ? [["expiration", "Expiration"], ["account", "Account"], ["region", "Region"], ["reservation", "Reservation"], ["utilization", "Utilization"]]
      : [["last_seen", "Last seen"], ["first_seen", "First seen"], ["severity", "Severity"]];
  const defaultSort = state.tab === "coverage" ? "account" : state.tab === "reservations" ? "expiration" : "last_seen";
  const defaultOrder = state.tab === "opportunities" ? "desc" : "asc";
  return (
    <div className={styles.sortControls}>
      <label>
        <span>Sort</span>
        <select value={state.sort || defaultSort} onChange={(event) => onChange({ sort: event.target.value, page: 1 })}>
          {options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </label>
      <label>
        <span>Order</span>
        <select value={state.sort ? state.order : defaultOrder} onChange={(event) => onChange({ order: event.target.value as "asc" | "desc", page: 1 })}>
          <option value="asc">Ascending</option>
          <option value="desc">Descending</option>
        </select>
      </label>
    </div>
  );
}

function TableState({ loading, error, empty, emptyTitle, emptyText, colSpan }: {
  loading: boolean;
  error: string;
  empty: boolean;
  emptyTitle: string;
  emptyText: string;
  colSpan: number;
}) {
  if (loading) {
    return <tbody>{Array.from({ length: 6 }, (_, index) => <tr key={index}><td colSpan={colSpan}><Skeleton className={styles.rowSkeleton} /></td></tr>)}</tbody>;
  }
  if (error) return <tbody><tr><td colSpan={colSpan}><div className={styles.tableError} role="alert"><AlertTriangle size={18} />{error}</div></td></tr></tbody>;
  if (empty) return <tbody><tr><td colSpan={colSpan}><div className={styles.tableEmpty}><Database size={24} /><strong>{emptyTitle}</strong><span>{emptyText}</span></div></td></tr></tbody>;
  return null;
}

function CoverageTable({ page, loading, error, onAccount }: { page?: RdsPage<RdsCoverageItem>; loading: boolean; error: string; onAccount: (account: string) => void }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const state = <TableState loading={loading} error={error} empty={!page?.items.length} emptyTitle="No RDS instances found" emptyText="No RDS workloads match the current filters." colSpan={10} />;
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead><tr><th aria-label="Details" /><th>Account</th><th>Region</th><th>DB Instance</th><th>Engine</th><th>Class</th><th>Topology</th><th><TooltipLabel label="Coverage" help="Percentage of current RDS capacity covered by compatible Reserved DB Instances." /></th><th><TooltipLabel label="Covered / Required" help="Normalized units compare compatible reservation capacity across supported instance sizes." /></th><th>Status</th></tr></thead>
        {state || <tbody>{page?.items.map((item) => {
          const isExpanded = expanded === item.instance_id;
          const tone = item.coverage_status === "FULL" ? "positive" : item.coverage_status === "PARTIAL" ? "warning" : item.coverage_status === "UNCOVERED" ? "critical" : "neutral";
          return <Fragment key={item.instance_id}>
            <tr>
              <td><button className={styles.expandButton} type="button" aria-label={`${isExpanded ? "Collapse" : "Expand"} ${item.instance}`} aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : item.instance_id)}>{isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button></td>
              <td title={accountLabel(item.account)}><button className={styles.accountButton} type="button" onClick={() => onAccount(item.account.account_id)}>{item.account.name || item.account.account_id}</button></td>
              <td>{item.region}</td><td className={styles.identifier} title={item.instance}>{item.instance}</td><td>{humanize(item.engine)}</td><td>{item.instance_class}</td><td>{humanize(item.topology)}</td>
              <td><div className={styles.coverageCell}><strong>{formatPercent(item.coverage_percentage)}</strong><Progress value={item.coverage_percentage} tone={tone} /></div></td>
              <td>{formatNu(item.covered_units)} / {formatNu(item.required_units)}</td>
              <td><Badge tone={coverageTone[item.coverage_status]}>{coverageStatusLabel(item.coverage_status)}</Badge></td>
            </tr>
            {isExpanded && <tr className={styles.detailRow}><td colSpan={10}><CoverageDetail item={item} /></td></tr>}
          </Fragment>;
        })}</tbody>}
      </table>
    </div>
  );
}

function CoverageDetail({ item }: { item: RdsCoverageItem }) {
  return (
    <div className={styles.detailGrid}>
      <section><span className={styles.kicker}>WORKLOAD</span><h3>{item.instance}</h3><dl>
        <div><dt>Account</dt><dd>{accountLabel(item.account)}</dd></div><div><dt>Region</dt><dd>{item.region}</dd></div><div><dt>Engine</dt><dd>{humanize(item.engine)} {item.engine_version || ""}</dd></div><div><dt>Class</dt><dd>{item.instance_class}</dd></div><div><dt>Family</dt><dd>{item.family}</dd></div><div><dt>Topology</dt><dd>{humanize(item.topology)}</dd></div><div><dt>License</dt><dd>{item.license_model || "—"}</dd></div>
      </dl></section>
      <section><span className={styles.kicker}>COVERAGE</span><h3>{formatPercent(item.coverage_percentage)}</h3><dl>
        <div><dt>Required</dt><dd>{formatNu(item.required_units)}</dd></div><div><dt>Covered</dt><dd>{formatNu(item.covered_units)}</dd></div><div><dt>Uncovered</dt><dd>{formatNu(item.uncovered_units)}</dd></div><div><dt>Scope</dt><dd>{humanize(item.coverage_scope)}</dd></div>
      </dl>
      {item.coverage_status === "UNKNOWN" && <p className={styles.neutralCallout}>{unknownReason(item.explanation)}</p>}
      {item.coverage_status === "UNCOVERED" && <p className={styles.warningCallout}>No compatible reserved capacity is currently allocated. Savings are not calculated on this screen.</p>}
      </section>
      <section className={styles.detailWide}><span className={styles.kicker}>RESERVATION ALLOCATIONS</span><h3>Why is this RDS {item.coverage_status === "UNCOVERED" ? "not covered" : "covered"}?</h3>
        {item.allocations.length ? <div className={styles.allocationList}>{item.allocations.map((allocation) => <div key={allocation.allocation_id}>
          <div><strong>{allocation.reservation_id}</strong><span>{allocation.reservation_class} · {accountLabel(allocation.reservation_account)}</span></div>
          <div><strong>{formatNu(allocation.allocated_units)}</strong><span>{formatPercent(allocation.allocation_percentage)}</span></div>
          <Badge tone={allocation.allocation_scope.includes("POTENTIAL") ? styles.warning : styles.neutral}>{allocation.allocation_scope.includes("POTENTIAL") ? "Potential cross-account" : humanize(allocation.allocation_scope)}</Badge>
        </div>)}</div> : <p className={styles.detailText}>No compatible reservation allocation was returned by the coverage engine.</p>}
        <details className={styles.explainability}><summary>Technical explainability</summary><pre>{JSON.stringify(item.explanation, null, 2)}</pre></details>
      </section>
    </div>
  );
}

function ReservationsTable({ page, loading, error, expiring = false, onAccount }: { page?: RdsPage<RdsReservationUtilization>; loading: boolean; error: string; expiring?: boolean; onAccount: (account: string) => void }) {
  const [expanded, setExpanded] = useState<number | null>(null);
  const emptyTitle = expiring ? "No reservations expiring in this range" : "No active RDS Reserved Instances found";
  const emptyText = expiring ? "No reservation matches the selected expiration window." : "RDS workloads can still be analyzed even when no active reservation exists.";
  const colSpan = expiring ? 10 : 11;
  const state = <TableState loading={loading} error={error} empty={!page?.items.length} emptyTitle={emptyTitle} emptyText={emptyText} colSpan={colSpan} />;
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead><tr><th aria-label="Details" /><th>Reservation</th><th>Account</th><th>Region</th><th>Engine</th><th>Class</th>{!expiring && <th>Quantity</th>}<th><TooltipLabel label="Utilization" help="Percentage of reserved capacity currently allocated to compatible RDS workloads." /></th><th>{expiring ? "Expiration" : "Unused"}</th><th>{expiring ? "Severity" : "Expiration"}</th><th>{expiring ? "Recommended action" : "Status"}</th></tr></thead>
        {state || <tbody>{page?.items.map((item) => {
          const isExpanded = expanded === item.reservation_id;
          return <Fragment key={item.reservation_id}>
            <tr>
              <td><button className={styles.expandButton} type="button" aria-label={`${isExpanded ? "Collapse" : "Expand"} ${item.reservation}`} aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : item.reservation_id)}>{isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button></td>
              <td className={styles.identifier} title={item.reservation}>{item.reservation}</td><td><button className={styles.accountButton} type="button" onClick={() => onAccount(item.account.account_id)}>{item.account.name || item.account.account_id}</button></td><td>{item.region}</td><td>{humanize(item.engine)}</td><td>{item.instance_class}</td>{!expiring && <td>{item.quantity}</td>}
              <td><div className={styles.coverageCell}><strong>{formatPercent(item.utilization_percentage)}</strong><Progress value={item.utilization_percentage} tone={item.utilization_percentage === 0 ? "critical" : item.utilization_percentage < 60 ? "warning" : "positive"} /><span>{formatNu(item.allocated_capacity)} / {formatNu(item.total_capacity)}</span></div></td>
              <td>{expiring ? <><strong>{formatDate(item.expiration_at)}</strong><span className={styles.subtle}>{item.days_remaining} days</span></> : formatNu(item.unused_capacity)}</td>
              <td>{expiring ? <Badge tone={item.expiration_severity === "high" ? styles.critical : styles.warning}>{severityLabels[item.expiration_severity || ""] || humanize(item.expiration_band)}</Badge> : <><strong>{formatDate(item.expiration_at)}</strong><span className={styles.subtle}>{item.days_remaining} days</span></>}</td>
              <td>{expiring ? <span className={styles.actionText}>{item.recommended_action || "Recommendation unavailable"}</span> : <Badge tone={item.state.toLowerCase() === "active" ? styles.positive : styles.neutral}>{humanize(item.state)}</Badge>}</td>
            </tr>
            {isExpanded && <tr className={styles.detailRow}><td colSpan={colSpan}><ReservationDetail item={item} /></td></tr>}
          </Fragment>;
        })}</tbody>}
      </table>
    </div>
  );
}

function ReservationDetail({ item }: { item: RdsReservationUtilization }) {
  return (
    <div className={styles.detailGrid}>
      <section><span className={styles.kicker}>RESERVATION</span><h3>{item.reservation}</h3><dl>
        <div><dt>Offering ID</dt><dd>{item.offering_id || "—"}</dd></div><div><dt>Account</dt><dd>{accountLabel(item.account)}</dd></div><div><dt>Engine</dt><dd>{humanize(item.engine)}</dd></div><div><dt>Class</dt><dd>{item.instance_class}</dd></div><div><dt>Quantity</dt><dd>{item.quantity}</dd></div><div><dt>Offering</dt><dd>{item.offering_type || "—"} · {item.offering_class || "—"}</dd></div><div><dt>Multi-AZ</dt><dd>{item.multi_az ? "Yes" : "No"}</dd></div><div><dt>Start</dt><dd>{formatDate(item.start_time)}</dd></div><div><dt>Expiration</dt><dd>{formatDate(item.expiration_at)} · {item.days_remaining} days</dd></div>
      </dl></section>
      <section><span className={styles.kicker}>CAPACITY</span><h3>{formatPercent(item.utilization_percentage)} utilized</h3><dl>
        <div><dt>Total reserved</dt><dd>{formatNu(item.total_capacity)}</dd></div><div><dt>Allocated</dt><dd>{formatNu(item.allocated_capacity)}</dd></div><div><dt>Unused</dt><dd>{formatNu(item.unused_capacity)}</dd></div>
      </dl><Progress value={item.utilization_percentage} tone={item.utilization_percentage < 60 ? "warning" : "positive"} /></section>
      <section className={styles.detailWide}><span className={styles.kicker}>WORKLOADS COVERED</span><h3>{item.workloads.length} allocation{item.workloads.length === 1 ? "" : "s"}</h3>
        {item.workloads.length ? <div className={styles.allocationList}>{item.workloads.map((workload) => <div key={workload.allocation_id}>
          <div><strong>{workload.instance}</strong><span>{accountLabel(workload.workload_account)}</span></div><div><strong>{formatNu(workload.allocated_units)}</strong><span>{humanize(workload.match_type)}</span></div><Badge tone={workload.allocation_scope.includes("POTENTIAL") ? styles.warning : styles.neutral}>{workload.allocation_scope.includes("POTENTIAL") ? "Potential" : workload.allocation_scope.includes("CROSS_ACCOUNT") ? "Cross-account · Verified" : humanize(workload.allocation_scope)}</Badge>
        </div>)}</div> : <p className={styles.detailText}>No RDS workload is consuming this reservation.</p>}
      </section>
    </div>
  );
}

function OpportunitiesTable({ page, loading, error, onAccount }: { page?: RdsPage<RdsReservationOpportunity>; loading: boolean; error: string; onAccount: (account: string) => void }) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const state = <TableState loading={loading} error={error} empty={!page?.items.length} emptyTitle="No active RDS reservation opportunities" emptyText="All reservation coverage signals match the current healthy state." colSpan={9} />;
  return (
    <div className={styles.tableScroll}>
      <table className={styles.table}>
        <thead><tr><th aria-label="Details" /><th>Type</th><th>Resource</th><th>Account</th><th>Region</th><th>Severity</th><th>Status</th><th>First seen</th><th>Last seen</th></tr></thead>
        {state || <tbody>{page?.items.map((item) => {
          const isExpanded = expanded === item.id;
          return <Fragment key={item.id}>
            <tr><td><button className={styles.expandButton} type="button" aria-label={`${isExpanded ? "Collapse" : "Expand"} opportunity`} aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : item.id)}>{isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</button></td><td><strong>{opportunityTypeLabel(item.type)}</strong></td><td className={styles.identifier}>{item.resource}</td><td><button className={styles.accountButton} type="button" onClick={() => onAccount(item.account_id)}>{item.account_name || item.account_id}</button></td><td>{item.region || "—"}</td><td><Badge tone={item.severity === "high" ? styles.critical : item.severity === "medium" ? styles.warning : styles.positive}>{severityLabels[item.severity] || humanize(item.severity)}</Badge></td><td><Badge>{humanize(item.status)}</Badge></td><td>{formatDate(item.first_seen_at)}</td><td>{formatDate(item.last_seen_at)}</td></tr>
            {isExpanded && <tr className={styles.detailRow}><td colSpan={9}><OpportunityDetail item={item} /></td></tr>}
          </Fragment>;
        })}</tbody>}
      </table>
    </div>
  );
}

function OpportunityDetail({ item }: { item: RdsReservationOpportunity }) {
  const metadata = item.metadata;
  const coverage = typeof metadata.coverage_percentage === "number" ? metadata.coverage_percentage : null;
  const unused = typeof metadata.unused_units === "number" ? metadata.unused_units : null;
  const days = typeof metadata.days_until_expiration === "number" ? metadata.days_until_expiration : null;
  return <div className={styles.opportunityDetail}><div><span className={styles.kicker}>{opportunityTypeLabel(item.type).toUpperCase()}</span><h3>{item.resource}</h3><p>{item.description}</p></div><dl>{coverage !== null && <div><dt>Current coverage</dt><dd>{formatPercent(coverage)}</dd></div>}{typeof metadata.required_units === "number" && <div><dt>Required capacity</dt><dd>{formatNu(metadata.required_units)}</dd></div>}{typeof metadata.covered_units === "number" && <div><dt>Covered capacity</dt><dd>{formatNu(metadata.covered_units)}</dd></div>}{typeof metadata.uncovered_units === "number" && <div><dt>Uncovered capacity</dt><dd>{formatNu(metadata.uncovered_units)}</dd></div>}{unused !== null && <div><dt>Unused capacity</dt><dd>{formatNu(unused)}</dd></div>}{days !== null && <div><dt>Days until expiration</dt><dd>{days}</dd></div>}</dl><div className={styles.recommendation}><strong>Recommended action</strong><p>{item.recommended_action || "No recommendation returned by the opportunity engine."}</p><small>Savings estimate: Not calculated</small></div></div>;
}

function Pagination({ page, onPage, onPageSize }: { page?: { page: number; page_size: number; total: number; total_pages: number }; onPage: (page: number) => void; onPageSize: (size: number) => void }) {
  if (!page || page.total === 0) return null;
  return <div className={styles.pagination}><span>{page.total.toLocaleString("pt-BR")} records</span><label>Rows <select value={page.page_size} onChange={(event) => onPageSize(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option><option value={200}>200</option></select></label><div><button type="button" disabled={page.page <= 1} onClick={() => onPage(page.page - 1)} aria-label="Previous page"><ChevronLeft size={16} /></button><span>Page {page.page} of {Math.max(1, page.total_pages)}</span><button type="button" disabled={page.page >= page.total_pages} onClick={() => onPage(page.page + 1)} aria-label="Next page"><ChevronRight size={16} /></button></div></div>;
}

export default function RdsReservationsPage() {
  return <Suspense fallback={<div className={styles.boot} role="status">Loading RDS reservations…</div>}><RdsReservationsContent /></Suspense>;
}

function RdsReservationsContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo(() => parseRdsReservationSearchParams(searchKey), [searchKey]);

  const update = (changes: Partial<RdsReservationQueryState>) => router.replace(`${pathname}${patchRdsReservationUrl(state, changes)}`, { scroll: false });
  const clear = () => router.replace(pathname, { scroll: false });

  const summaryQuery = buildRdsDashboardQuery(state, "summary");
  const optionsQuery = buildRdsDashboardQuery(state, "options");
  const mainKind = state.tab === "coverage" ? "coverage" : state.tab === "reservations" ? "reservations" : state.tab === "expiring" ? "expiring" : "opportunities";
  const mainQuery = buildRdsDashboardQuery(state, mainKind);
  const summary = useApiQuery<RdsReservationsSummary>({ key: ["rds-reservations", "summary", summaryQuery], path: `/rds/reservations-dashboard/summary${summaryQuery ? `?${summaryQuery}` : ""}`, ...cachePolicy.operational });
  const options = useApiQuery<RdsReservationsOptions>({ key: ["rds-reservations", "options"], path: `/rds/reservations-dashboard/options${optionsQuery ? `?${optionsQuery}` : ""}`, ...cachePolicy.metadata });
  const coverage = useApiQuery<RdsPage<RdsCoverageItem>>({ key: ["rds-reservations", "coverage", mainQuery], path: `/rds/reservations-dashboard/coverage?${mainQuery}`, enabled: state.tab === "coverage", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });
  const reservations = useApiQuery<RdsPage<RdsReservationUtilization>>({ key: ["rds-reservations", state.tab, mainQuery], path: `/rds/reservations-dashboard/reservations?${mainQuery}`, enabled: state.tab === "reservations" || state.tab === "expiring", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });
  const opportunities = useApiQuery<RdsPage<RdsReservationOpportunity>>({ key: ["rds-reservations", "opportunities", mainQuery], path: `/rds/reservations-dashboard/opportunities?${mainQuery}`, enabled: state.tab === "opportunities", keepPreviousData: true, placeholderIdentity: JSON.stringify({ ...state, page: 0 }), ...cachePolicy.operational });

  const main = state.tab === "coverage" ? coverage : state.tab === "opportunities" ? opportunities : reservations;
  const refreshAll = () => { void summary.refetch(); void options.refetch(); void main.refetch(); };
  const summaryError = summary.error ? queryError(summary.error, "Could not load RDS reservation summary.") : "";
  const mainError = main.error ? queryError(main.error, "Could not load RDS reservation data.") : "";
  const noCoverageRun = summary.error instanceof ApiError && summary.error.status === 404;

  return (
    <div className={styles.page}>
      <PageHeader eyebrow="AWS · FINOPS COMMITMENTS" title="RDS Reservations" description="Analyze technical coverage, reserved-capacity utilization, expirations and reservation opportunities without mixing current inventory with historical AWS billing observations." actions={<button className="button ghost" type="button" onClick={refreshAll} disabled={summary.isFetching || main.isFetching}><RefreshCw size={16} className={summary.isFetching || main.isFetching ? styles.spinning : ""} />Refresh</button>} />

      {summaryError && <div className={styles.pageAlert} role="alert"><AlertTriangle size={18} /><div><strong>{noCoverageRun ? "Coverage not calculated yet" : "Summary unavailable"}</strong><span>{summaryError}</span></div></div>}

      <section className={styles.metrics} aria-label="RDS reservation summary">
        <MetricCard label="Total RDS" value={summary.data?.rds.total || 0} detail="Eligible workloads analyzed" loading={summary.isLoading} icon={<Database size={18} />} />
        <MetricCard label="Full Coverage" value={summary.data?.rds.fully_covered || 0} detail={`${formatPercent(summary.data?.rds.total ? (summary.data.rds.fully_covered / summary.data.rds.total) * 100 : 0)} of workloads`} loading={summary.isLoading} icon={<ShieldCheck size={18} />} />
        <MetricCard label="Partial Coverage" value={summary.data?.rds.partially_covered || 0} detail="Workloads with an explicit gap" loading={summary.isLoading} icon={<Gauge size={18} />} />
        <MetricCard label="Uncovered" value={summary.data?.rds.uncovered || 0} detail={`${summary.data?.rds.unknown || 0} unknown kept separate`} loading={summary.isLoading} icon={<AlertTriangle size={18} />} />
        <MetricCard label="Reserved Capacity Utilization" value={formatPercent(summary.data?.reservations.utilization_percentage || 0)} detail={`${formatNu(summary.data?.reservations.used_units || 0)} / ${formatNu(summary.data?.reservations.reserved_units || 0)}`} loading={summary.isLoading} icon={<Cloud size={18} />} />
        <MetricCard label="Expiring ≤30 days" value={summary.data?.expiring_next_30_days || 0} detail="Backend-classified active reservations" loading={summary.isLoading} icon={<TimerReset size={18} />} />
      </section>

      <section className={styles.overviewGrid}>
        <StatusDistribution summary={summary.data} loading={summary.isLoading} />
        <CapacityOverview summary={summary.data} loading={summary.isLoading} />
      </section>

      <section className={styles.coverageHeadline}>
        <div><TooltipLabel label="Coverage" help="Primary coverage uses covered normalized units divided by required normalized units, not the count of covered RDS instances." />{summary.isLoading ? <Skeleton className={styles.coverageSkeleton} /> : <strong>{formatPercent(summary.data?.coverage.coverage_percentage || 0)}</strong>}<span>{formatNu(summary.data?.coverage.covered_units || 0)} / {formatNu(summary.data?.coverage.required_units || 0)} covered</span></div>
        <div><span>Workloads fully covered</span><strong>{summary.data?.rds.fully_covered || 0} of {summary.data?.rds.total || 0}</strong></div>
        <div className={styles.freshness}><span>Inventory <strong>{relativeTime(summary.data?.freshness.inventory_updated_at)}</strong></span><span>Coverage <strong>{relativeTime(summary.data?.freshness.coverage_calculated_at)}</strong></span><span>AWS billing <strong>{summary.data?.billing.validation_status === "AVAILABLE" ? summary.data.freshness.billing_data_reference || "completed period" : "unavailable"}</strong></span></div>
      </section>

      <BillingCoverage summary={summary.data} loading={summary.isLoading} />
      <Filters state={state} options={options.data} onChange={update} onClear={clear} />

      <section className={styles.dataPanel}>
        <div className={styles.tabs} role="tablist" aria-label="RDS reservation views">
          {(Object.entries(tabLabels) as [RdsReservationQueryState["tab"], string][]).map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={state.tab === value} className={state.tab === value ? styles.activeTab : ""} onClick={() => update({ tab: value, page: 1, sort: "", order: value === "opportunities" ? "desc" : "asc" })}>{label}</button>)}
        </div>
        <div className={styles.tableHeader}><div><strong>{tabLabels[state.tab]}</strong><span>{state.tab === "coverage" ? "Current RDS workloads and compatible reserved-capacity allocations." : state.tab === "reservations" ? "Reserved DB Instances, allocated capacity and unused capacity." : state.tab === "expiring" ? "Reservations ordered by expiration; severity and actions come from the backend opportunity engine." : "Active RDS reservation opportunities generated by Task 23.31."}</span></div><div className={styles.tableActions}><SortControls state={state} onChange={update} />{main.isFetching && !main.isLoading && <span className={styles.refreshing}><RefreshCw size={13} className={styles.spinning} />Updating</span>}</div></div>
        {state.tab === "coverage" && <CoverageTable page={coverage.data} loading={coverage.isLoading} error={mainError} onAccount={(account) => update({ account, page: 1 })} />}
        {state.tab === "reservations" && <ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} onAccount={(account) => update({ account, page: 1 })} />}
        {state.tab === "expiring" && <ReservationsTable page={reservations.data} loading={reservations.isLoading} error={mainError} expiring onAccount={(account) => update({ account, page: 1 })} />}
        {state.tab === "opportunities" && <OpportunitiesTable page={opportunities.data} loading={opportunities.isLoading} error={mainError} onAccount={(account) => update({ account, page: 1 })} />}
        <Pagination page={main.data} onPage={(page) => update({ page })} onPageSize={(pageSize) => update({ pageSize, page: 1 })} />
      </section>

      <p className={styles.scopeNote}>This view does not calculate acquisition savings, purchase offers, break-even, 1-year vs 3-year recommendations or execute Reserved DB Instance purchases.</p>
    </div>
  );
}
