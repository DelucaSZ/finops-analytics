"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { History, LockKeyhole, RefreshCw } from "lucide-react";
import {
  DataState,
  FilterBar,
  FilterItem,
  MetricCard,
  PageHeader,
  ProviderBadge,
  Section,
  StatusIndicator,
} from "@/components/aven";
import {
  Alert,
  Button,
  Input,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableState,
} from "@/components/ui";
import { api, formatDate } from "@/lib/api";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import {
  buildHistorySnapshotQuery,
  chooseHistoryCycle,
  cycleStateLabel,
  historyMoneyRows,
} from "@/lib/opportunity-history.mjs";
import styles from "./page.module.css";

type MoneyTotal = { currency: string; amount: string | number };
type Coverage = { total: number; success: number; failed: number; running: number };
type Cycle = {
  id: string;
  label: string;
  period_start: string;
  period_end: string;
  status: "OPEN" | "CLOSED";
  timezone: string;
  created_at: string;
  closed_at: string | null;
  closed_by: string | null;
  close_reason: string | null;
  snapshot_count: number;
  totals: {
    total?: number;
    by_status?: Record<string, number>;
    by_severity?: Record<string, number>;
    potential_savings?: MoneyTotal[];
    current_cost?: MoneyTotal[];
    financial_coverage?: Array<{ currency: string; known: number; partial: number; unknown: number; complete: boolean }>;
    providers?: number;
    accounts?: number;
  };
  coverage: Coverage;
};
type Snapshot = {
  id: string;
  cycle_id: string;
  opportunity_id: string | null;
  provider: string;
  account_id: string;
  account_name: string | null;
  region: string | null;
  service: string;
  resource_type: string | null;
  resource_id: string;
  resource_name: string | null;
  rule_key: string;
  title: string;
  description: string;
  status: string;
  presence_status: string;
  needs_review: boolean;
  archived: boolean;
  archive_reason: string | null;
  treated_at: string | null;
  rejected_at: string | null;
  resolved_externally_at: string | null;
  treatment_note: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  current_monthly_cost: string | number | null;
  estimated_monthly_savings: string | number | null;
  currency: string;
  severity: string;
  confidence: string;
  first_seen_at: string;
  last_seen_at: string;
  first_observed_in_cycle_at: string;
  last_observed_in_cycle_at: string;
  occurrence_count_in_cycle: number;
  total_occurrence_count: number;
  first_collection_run_id_in_cycle: string | null;
  last_collection_run_id_in_cycle: string | null;
  captured_at: string;
};
type SnapshotPage = {
  items: Snapshot[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

function statusTone(status: string) {
  if (status === "treated") return "success" as const;
  if (status === "rejected") return "neutral" as const;
  return "info" as const;
}

function presenceTone(status: string) {
  if (status === "missing") return "warning" as const;
  if (status === "resolved_externally") return "success" as const;
  return "info" as const;
}

function severityTone(severity: string) {
  if (severity === "high") return "danger" as const;
  if (severity === "medium") return "warning" as const;
  return "neutral" as const;
}

export default function OpportunityHistoryCyclesPage() {
  const locale = useLocale();
  const t = useTranslations("opportunities.cycles");
  const statusT = useTranslations("opportunities.status");
  const severityT = useTranslations("opportunities.severity");
  const statusLabel = (value:string) => value === "resolved_externally" ? statusT("resolvedExternally") : ["open","treated","rejected","active","missing"].includes(value) ? statusT(value as "open" | "treated" | "rejected" | "active" | "missing") : value;
  const presenceLabel = (value:string) => statusLabel(value);
  const cycleState = (value:string) => value === "CLOSED" ? t("cycle.closed") : value === "OPEN" ? t("cycle.open") : cycleStateLabel(value);
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [cycleId, setCycleId] = useState("");
  const [snapshots, setSnapshots] = useState<SnapshotPage>({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [page, setPage] = useState(1);
  const [provider, setProvider] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(false);
  const [error, setError] = useState("");

  const cycle = useMemo(() => cycles.find((item) => item.id === cycleId) ?? null, [cycles, cycleId]);
  const savings = historyMoneyRows(cycle?.totals, "potential_savings") as MoneyTotal[];
  const costs = historyMoneyRows(cycle?.totals, "current_cost") as MoneyTotal[];
  const incompleteFinancialCoverage = cycle?.totals.financial_coverage?.some((item) => !item.complete) ?? false;

  async function loadCycles(preferredId = cycleId) {
    setError("");
    const current = await api<Cycle>("/opportunity-history/cycles/current");
    const response = await api<{ items: Cycle[]; total: number }>("/opportunity-history/cycles");
    const items = response.items.some((item) => item.id === current.id)
      ? response.items
      : [current, ...response.items];
    setCycles(items);
    const next = chooseHistoryCycle(items, preferredId) as Cycle | null;
    setCycleId(next?.id ?? "");
    return next;
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadCycles().catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : t("errors.cycles"));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
    // Initial bootstrap only. Subsequent refreshes are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!cycleId) return;
    const chosen = cycles.find((item) => item.id === cycleId);
    setSelected(null);
    if (!chosen || chosen.status !== "CLOSED") {
      setSnapshots({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      const query = buildHistorySnapshotQuery({ cycleId, page, pageSize: 50, provider, status, severity, search });
      api<SnapshotPage>(`/opportunity-history/snapshots?${query}`).then((response) => {
        if (active) setSnapshots(response);
      }).catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : t("errors.snapshots"));
      });
    }, search ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [cycleId, cycles, page, provider, search, severity, status]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      await loadCycles(cycleId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("errors.refresh"));
    } finally {
      setLoading(false);
    }
  }

  async function closeSelectedCycle() {
    if (!cycle || cycle.status !== "OPEN") return;
    setClosing(true);
    setError("");
    try {
      await api(`/opportunity-history/cycles/${cycle.id}/close`, { method: "POST" });
      await loadCycles(cycle.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : t("errors.close"));
    } finally {
      setClosing(false);
    }
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        metadata={t("metadata")}
        actions={(
          <Button
            variant="secondary"
            leadingIcon={<RefreshCw {...iconDefaults} />}
            onClick={refresh}
            disabled={loading}
          >
            {loading ? t("refreshing") : t("refresh")}
          </Button>
        )}
      />

      <nav className={styles.switcher} aria-label={t("navAria")}>
        <span aria-current="page"><History {...iconDefaults} /> {t("nav.closed")}</span>
        <Link href="/opportunities?view=history">{t("nav.legacy")}</Link>
        <Link href="/opportunities">{t("nav.backlog")}</Link>
      </nav>

      {error && <Alert variant="danger" title={t("errorTitle")} description={error} />}

      <FilterBar className={styles.filterBar}>
        <FilterItem size="wide">
          <Select
            id="history-cycle"
            label={t("filters.period")}
            value={cycleId}
            options={cycles.map((item) => ({
              value: item.id,
              label: `${item.label} — ${cycleState(item.status)}`,
            }))}
            onChange={(event) => { setCycleId(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="compact">
          <Select
            id="history-provider"
            label={t("filters.cloud")}
            value={provider}
            options={[
              { value: "", label: t("filters.allFeminine") },
              { value: "aws", label: "AWS" },
              { value: "oci", label: "OCI" },
            ]}
            onChange={(event) => { setProvider(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="default">
          <Select
            id="history-status"
            label={t("filters.status")}
            value={status}
            options={[
              { value: "", label: t("filters.allMasculine") },
              { value: "open", label: statusT("open") },
              { value: "treated", label: statusT("treated") },
              { value: "rejected", label: statusT("rejected") },
            ]}
            onChange={(event) => { setStatus(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="compact">
          <Select
            id="history-severity"
            label={t("filters.severity")}
            value={severity}
            options={[
              { value: "", label: t("filters.allFeminine") },
              { value: "high", label: severityT("high") },
              { value: "medium", label: severityT("medium") },
              { value: "low", label: severityT("low") },
            ]}
            onChange={(event) => { setSeverity(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="wide">
          <Input
            id="history-search"
            label={t("filters.search")}
            type="search"
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
            placeholder={t("filters.searchPlaceholder")}
          />
        </FilterItem>
      </FilterBar>

      {cycle && (
        <Section
          appearance="card"
          title={`${cycle.label} · ${cycleState(cycle.status)}`}
          description={`${formatDate(cycle.period_start, locale)} ${t("detail.periodTo")} ${formatDate(cycle.period_end, locale)} · ${t("detail.timezone")} ${cycle.timezone}${cycle.closed_at ? ` · ${t("cycle.closedAt",{date:formatDate(cycle.closed_at, locale)})}` : ` · ${t("cycle.preview")}`}`}
          actions={cycle.status === "OPEN" ? (
            <Button
              leadingIcon={<LockKeyhole {...iconDefaults} />}
              loading={closing}
              disabled={closing || cycle.coverage.running > 0}
              onClick={closeSelectedCycle}
            >
              Fechar ciclo
            </Button>
          ) : undefined}
        >
          <div className={styles.cycleMeta}>
            <StatusIndicator
              status={cycle.status === "CLOSED" ? "success" : "pending"}
              label={cycleState(cycle.status)}
            />
            <span>{t("cycle.coverage",{success:cycle.coverage.success,failed:cycle.coverage.failed,running:cycle.coverage.running})}</span>
          </div>
        </Section>
      )}

      {cycle && (
        <Section title={t("summary.title")} description={t("summary.description")}>
          <div className={styles.summary}>
            <MetricCard
              label={t("summary.opportunities")}
              value={cycle.status === "CLOSED" ? cycle.snapshot_count : "—"}
              supportingText={cycle.status === "CLOSED" ? t("summary.immutable") : t("summary.afterClose")}
              icon={<History {...iconDefaults} />}
            />
            <MetricCard
              label={t("summary.potential")}
              value={savings.length ? (
                <span className={styles.moneyList}>
                  {savings.map((row) => <span key={row.currency}>{formatMoney(row.amount, row.currency, locale)}{t("detail.perMonth")}</span>)}
                </span>
              ) : "—"}
              supportingText={incompleteFinancialCoverage ? t("summary.incompleteFinancialCoverage") : t("summary.noFx")}
            />
            <MetricCard
              label={t("summary.current")}
              value={costs.length ? (
                <span className={styles.moneyList}>
                  {costs.map((row) => <span key={row.currency}>{formatMoney(row.amount, row.currency, locale)}{t("detail.perMonth")}</span>)}
                </span>
              ) : "—"}
              supportingText={t("summary.captured")}
            />
            <MetricCard
              label={t("summary.collections")}
              value={cycle.coverage.total}
              supportingText={t("summary.coverage",{success:cycle.coverage.success,failed:cycle.coverage.failed,running:cycle.coverage.running})}
            />
          </div>
        </Section>
      )}

      {cycle?.status === "OPEN" ? (
        <Section appearance="card">
          <DataState
            empty
            emptyTitle={t("cycle.preview")}
            emptyDescription={t("snapshot.previewDescription")}
          >
            <span />
          </DataState>
        </Section>
      ) : (
        <Section
          title={t("snapshot.title")}
          description={t("snapshot.description")}
        >
          <Table density="compact" aria-label={t("snapshot.aria")}>
            <TableHeader>
              <TableRow staticRow>
                <TableHead kind="identifier">{t("snapshot.opportunity")}</TableHead>
                <TableHead kind="text">{t("snapshot.accountCloud")}</TableHead>
                <TableHead kind="status">{t("snapshot.status")}</TableHead>
                <TableHead kind="badge">{t("snapshot.severity")}</TableHead>
                <TableHead kind="currency" numeric>{t("snapshot.cost")}</TableHead>
                <TableHead kind="currency" numeric>{t("snapshot.savings")}</TableHead>
                <TableHead kind="numeric" numeric>{t("snapshot.observations")}</TableHead>
                <TableHead kind="date">{t("snapshot.lastObserved")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {snapshots.items.map((item) => (
                <TableRow key={item.id}>
                  <TableCell kind="identifier">
                    <button type="button" className={styles.rowButton} onClick={() => setSelected(item)}>
                      <strong>{item.title}</strong>
                      <span>{item.resource_name || item.resource_id}</span>
                    </button>
                  </TableCell>
                  <TableCell kind="text">
                    {item.account_name || item.account_id}
                    <div className={styles.providerLine}><ProviderBadge provider={item.provider} /></div>
                  </TableCell>
                  <TableCell kind="status">
                    <div className={styles.statusStack}>
                      <StatusIndicator status={statusTone(item.status)} label={statusLabel(item.status)} />
                      <StatusIndicator status={presenceTone(item.presence_status)} label={presenceLabel(item.presence_status)} />
                    </div>
                  </TableCell>
                  <TableCell kind="badge"><StatusIndicator status={severityTone(item.severity)} label={["high","medium","low"].includes(item.severity) ? severityT(item.severity as "high" | "medium" | "low") : item.severity} /></TableCell>
                  <TableCell kind="currency" numeric>{item.current_monthly_cost == null ? "—" : formatMoney(item.current_monthly_cost, item.currency, locale)}</TableCell>
                  <TableCell kind="currency" numeric>{item.estimated_monthly_savings == null ? "—" : formatMoney(item.estimated_monthly_savings, item.currency, locale)}</TableCell>
                  <TableCell kind="numeric" numeric>{item.occurrence_count_in_cycle}</TableCell>
                  <TableCell kind="date">{formatDate(item.last_observed_in_cycle_at, locale)}</TableCell>
                </TableRow>
              ))}
              {!snapshots.items.length && (
                <TableRow staticRow>
                  <TableState state="empty" colSpan={8}>{t("snapshot.empty")}</TableState>
                </TableRow>
              )}
            </TableBody>
          </Table>
          <div className={styles.footer}>
            <span>{t("snapshot.page",{count:snapshots.total,page:snapshots.page || 1,total:snapshots.total_pages || 1})}</span>
            <div className={styles.footerActions}>
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>{t("snapshot.previous")}</Button>
              <Button variant="secondary" disabled={!snapshots.total_pages || page >= snapshots.total_pages} onClick={() => setPage((value) => value + 1)}>{t("snapshot.next")}</Button>
            </div>
          </div>
        </Section>
      )}

      {selected && (
        <Section
          appearance="card"
          title={selected.title}
          description={selected.description}
          actions={<Button variant="secondary" onClick={() => setSelected(null)}>{t("detail.close")}</Button>}
          aria-label={`Snapshot ${selected.title}`}
        >
          <dl className={styles.detailGrid}>
            <div><dt>{t("detail.cloud")}</dt><dd>{providerLabel(selected.provider)}</dd></div>
            <div><dt>{t("detail.account")}</dt><dd>{selected.account_name || selected.account_id}</dd></div>
            <div><dt>{t("detail.resource")}</dt><dd>{selected.resource_name || selected.resource_id}</dd></div>
            <div><dt>{t("detail.rule")}</dt><dd>{selected.rule_key}</dd></div>
            <div><dt>{t("detail.serviceRegion")}</dt><dd>{selected.service} · {selected.region || "—"}</dd></div>
            <div><dt>{t("detail.status")}</dt><dd>{statusLabel(selected.status)}</dd></div>
            <div><dt>{t("detail.presence")}</dt><dd>{presenceLabel(selected.presence_status)}</dd></div>
            <div><dt>{t("detail.severityConfidence")}</dt><dd>{(["high","medium","low"].includes(selected.severity) ? severityT(selected.severity as "high" | "medium" | "low") : selected.severity)} · {(["high","medium","low"].includes(selected.confidence) ? severityT(selected.confidence as "high" | "medium" | "low") : selected.confidence)}</dd></div>
            <div><dt>{t("detail.archived")}</dt><dd>{selected.archived ? `${t("detail.yes")}${selected.archive_reason ? ` · ${selected.archive_reason}` : ""}` : t("detail.no")}</dd></div>
            <div><dt>{t("detail.periodCost")}</dt><dd>{selected.current_monthly_cost == null ? "—" : formatMoney(selected.current_monthly_cost, selected.currency, locale)}{t("detail.perMonth")}</dd></div>
            <div><dt>{t("detail.estimatedSavings")}</dt><dd>{selected.estimated_monthly_savings == null ? "—" : formatMoney(selected.estimated_monthly_savings, selected.currency, locale)}{t("detail.perMonth")}</dd></div>
            <div><dt>{t("detail.firstObserved")}</dt><dd>{formatDate(selected.first_observed_in_cycle_at, locale)}</dd></div>
            <div><dt>{t("detail.lastObserved")}</dt><dd>{formatDate(selected.last_observed_in_cycle_at, locale)}</dd></div>
            <div><dt>{t("detail.occurrences")}</dt><dd>{selected.occurrence_count_in_cycle}</dd></div>
            <div><dt>{t("detail.firstSeen")}</dt><dd>{formatDate(selected.first_seen_at, locale)}</dd></div>
            <div><dt>{t("detail.lastSeen")}</dt><dd>{formatDate(selected.last_seen_at, locale)}</dd></div>
            <div><dt>{t("detail.lastCollection")}</dt><dd>{selected.last_collection_run_id_in_cycle || "—"}</dd></div>
          </dl>
          <div className={styles.detailNotes}>
            {selected.rejection_reason && <p><strong>{t("detail.rejectReason")}</strong> {selected.rejection_reason}{selected.rejection_note ? ` — ${selected.rejection_note}` : ""}</p>}
            {selected.treatment_note && <p><strong>{t("detail.treatment")}</strong> {selected.treatment_note}</p>}
            {selected.opportunity_id && (
              <p><Link href={`/opportunities?resource_id=${encodeURIComponent(selected.resource_id)}`}>{t("detail.openCurrent")}</Link> <span className={styles.secondary}>{t("detail.independent")}</span></p>
            )}
          </div>
        </Section>
      )}
    </div>
  );
}
