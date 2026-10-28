"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Archive,
  CalendarClock,
  RefreshCw,
  Search,
  WalletCards,
} from "lucide-react";
import { OpportunityArchiveDialog } from "@/components/opportunity-archive-dialog";
import { OpportunityDecisionDialog } from "@/components/opportunity-decision-dialog";
import type { OpportunityDecisionAction } from "@/components/opportunity-decision-dialog";
import { OpportunityDetail } from "@/components/opportunity-detail";
import {
  AccountSelector,
  CurrencyDisplay,
  DataState,
  FilterBar,
  MetricCard,
  PageHeader,
  ProviderBadge,
  ProviderSelector,
  RecommendationCard,
  ResourceIdentifier,
  Section,
  StatusIndicator,
} from "@/components/aven";
import type { ProductStatus } from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Input,
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
  TabsList,
  TabsTrigger,
} from "@/components/ui";
import { api, formatDate } from "@/lib/api";
import { formatAccountLabel, providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import {
  invalidateApiQueries,
  prefetchApiQuery,
  useApiQuery,
} from "@/lib/server-state";
import {
  buildLifecycleRequest,
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
} from "@/lib/opportunity-query.mjs";
import type { OpportunityQueryState } from "@/lib/opportunity-query.mjs";
import type {
  CollectionRun,
  Finding,
  OpportunityOptions,
  OpportunityPage,
  OpportunityStats,
} from "@/lib/types";
import styles from "./opportunities.module.css";

const statusTabs = [
  { value: "open", label: "Abertas" },
  { value: "treated", label: "Tratadas" },
  { value: "rejected", label: "Rejeitadas" },
] as const;

const rejectionFallback = "Não foi possível atualizar a oportunidade. Nenhuma alteração foi aplicada.";

const operationalSortOptions = [
  { value: "last_seen_at", label: "Última detecção" },
  { value: "first_seen_at", label: "Primeira detecção" },
  { value: "severity", label: "Severidade" },
  { value: "estimated_savings", label: "Economia potencial" },
  { value: "created_at", label: "Criação" },
];

const historySortOptions = [
  { value: "archived_at", label: "Data de arquivamento" },
  { value: "last_seen_at", label: "Última observação" },
  { value: "status", label: "Status humano" },
  { value: "estimated_savings", label: "Economia potencial" },
];

const archiveReasonLabels: Record<string, string> = {
  MANUAL: "Manual",
  RETENTION_POLICY: "Política de retenção",
};

const temporalPresetLabels: Record<string, string> = {
  today: "Hoje",
  last_24h: "Últimas 24h",
  last_7d: "Últimos 7 dias",
  last_30d: "Últimos 30 dias",
  custom: "Período personalizado",
};

const discoveryTypeLabels: Record<string, string> = {
  observed: "Observadas nesta coleta",
  first_seen: "Identificadas pela primeira vez nesta coleta",
  new_vs_previous: "Novas em relação à coleta anterior",
  reappeared: "Reapareceram nesta coleta",
  continued: "Continuaram presentes",
};

type HistoricalFinding = Finding & {
  archived: boolean;
  archived_at: string | null;
  archived_by: string | null;
  archive_reason: string | null;
};

type ArchiveDialogState = {
  mode: "individual" | "selected" | "filter" | "period";
  opportunityId?: string;
  opportunityIds?: string[];
};

function humanize(value?: string | null) {
  if (!value) return "—";
  return value
    .replaceAll("-", "_")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function numericValue(value?: string | number | null) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function statusLabel(value: string) {
  if (value === "open") return "Aberta";
  if (value === "treated") return "Tratada";
  if (value === "rejected") return "Rejeitada";
  if (value === "active") return "Ativa";
  if (value === "missing") return "Ausente";
  if (value === "resolved_externally") return "Resolvida externamente";
  return humanize(value);
}

function statusTone(value: string): ProductStatus {
  if (value === "treated" || value === "active" || value === "resolved_externally") return "success";
  if (value === "rejected") return "danger";
  if (value === "missing") return "warning";
  if (value === "open") return "info";
  return "neutral";
}

function severityTone(value: string): ProductStatus {
  if (value === "high") return "danger";
  if (value === "medium") return "warning";
  if (value === "low") return "info";
  return "neutral";
}

function confidenceTone(value: string): ProductStatus {
  const normalized = value.trim().toLowerCase();
  if (normalized === "high") return "success";
  if (normalized === "medium") return "info";
  if (normalized === "low") return "warning";
  return "neutral";
}

function MoneyValue({ value, currency }: { value: string | number | null | undefined; currency: string }) {
  const amount = numericValue(value);
  if (!currency || amount == null) return <span>—</span>;
  return <CurrencyDisplay value={amount} currency={currency} locale="pt-BR" maximumFractionDigits={2} />;
}

function SavingsValue({ finding }: { finding: Finding }) {
  if (finding.rule_key === "cost_growth_anomaly") return <span>Não estimada</span>;
  return (
    <span className={styles.moneyWithPeriod}>
      <MoneyValue value={finding.estimated_monthly_savings} currency={finding.currency} />
      <span>/mês</span>
    </span>
  );
}

function activeOption(values: string[], current: string) {
  return Array.from(new Set([...values, ...(current ? [current] : [])]));
}

function OpportunityLoadingRows({ history }: { history: boolean }) {
  return (
    <TableBody aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <TableRow key={index} staticRow>
          {!history ? <TableCell><Skeleton /></TableCell> : null}
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
          <TableCell><Skeleton /></TableCell>
        </TableRow>
      ))}
    </TableBody>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<div className={styles.page}><Skeleton /><Skeleton /><Skeleton /></div>}>
      <OpportunitiesContent />
    </Suspense>
  );
}

function OpportunitiesContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<OpportunityQueryState>(() => parseOpportunitySearchParams(searchKey), [searchKey]);
  const isHistory = state.view === "history";
  const temporalAnchor = useMemo(() => new Date(), [searchKey]);

  const listQuery = useMemo(
    () => buildOpportunityApiQuery(state, { now: temporalAnchor }),
    [state, temporalAnchor],
  );
  const statsQuery = useMemo(
    () => buildOpportunityStatsQuery({
      ...state,
      view: "operational",
      status: "open",
      presenceStatus: "",
      archivedFrom: "",
      archivedTo: "",
      archiveReason: "",
      current: isHistory ? false : state.current,
    }, { now: temporalAnchor }),
    [isHistory, state, temporalAnchor],
  );

  const optionsQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "300" });
    if (state.provider) params.set("provider", state.provider);
    if (state.accountId) params.set("account_id", state.accountId);
    if (isHistory) params.set("archive_state", "archived");
    return params.toString();
  }, [isHistory, state.accountId, state.provider]);

  const listPlaceholderIdentity = useMemo(
    () => JSON.stringify({
      view: state.view,
      status: state.status,
      presenceStatus: state.presenceStatus,
      provider: state.provider,
      accountId: state.accountId,
      region: state.region,
      service: state.service,
      resourceType: state.resourceType,
      severity: state.severity,
      rule: state.rule,
      collectionRunId: state.collectionRunId,
      firstSeenCollectionRunId: state.firstSeenCollectionRunId,
      discoveryType: state.discoveryType,
      resourceId: state.resourceId,
      search: state.search,
      dateField: state.dateField,
      temporalPreset: state.temporalPreset,
      temporalFrom: state.temporalFrom,
      temporalTo: state.temporalTo,
      current: state.current,
      archivedFrom: state.archivedFrom,
      archivedTo: state.archivedTo,
      archiveReason: state.archiveReason,
      pageSize: state.pageSize,
      sort: state.sort,
      order: state.order,
    }),
    [state],
  );

  const optionsRequest = useApiQuery<OpportunityOptions>({
    key: ["opportunities", "options", state.view, state.provider, state.accountId],
    path: `/opportunities/options?${optionsQuery}`,
    ...cachePolicy.metadata,
  });
  const collectionRunsRequest = useApiQuery<CollectionRun[]>({
    key: queryKeys.collections.picker(),
    path: "/collections?limit=100&offset=0",
    ...cachePolicy.operational,
  });
  const listRequest = useApiQuery<OpportunityPage>({
    key: queryKeys.opportunities.list(listQuery),
    path: `/opportunities?${listQuery}`,
    ...cachePolicy.operational,
    keepPreviousData: true,
    placeholderIdentity: listPlaceholderIdentity,
  });
  const statsRequest = useApiQuery<OpportunityStats>({
    key: queryKeys.opportunities.stats(statsQuery),
    path: `/opportunities/stats${statsQuery ? `?${statsQuery}` : ""}`,
    ...cachePolicy.operational,
  });

  const findings = (listRequest.data?.items ?? []) as HistoricalFinding[];
  const options = optionsRequest.data ?? {
    providers: [],
    accounts: [],
    regions: [],
    services: [],
    resource_types: [],
    rules: [],
  };
  const collectionRuns = collectionRunsRequest.data ?? [];
  const stats = statsRequest.data ?? { open: 0, treated: 0, rejected: 0 };
  const total = listRequest.data?.total ?? 0;
  const totalPages = listRequest.data?.total_pages ?? 0;
  const loading = listRequest.isLoading || listRequest.isFetching;
  const statsLoading = statsRequest.isLoading;
  const filtersLoading = optionsRequest.isLoading;
  const listError = listRequest.error?.message || "";
  const filterError = optionsRequest.error?.message || "";

  const [message, setMessage] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState(state.search);
  const [unarchiveSavingId, setUnarchiveSavingId] = useState("");
  const [archiveDialog, setArchiveDialog] = useState<ArchiveDialogState | null>(null);
  const [decision, setDecision] = useState<{ action: OpportunityDecisionAction; ids: string[]; bulk: boolean } | null>(null);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");

  const updateUrl = useCallback((patch: Record<string, string | number | boolean | null | undefined>, optionsValue?: { resetPage?: boolean; push?: boolean }) => {
    const params = patchOpportunityUrl(searchKey, patch, { resetPage: optionsValue?.resetPage });
    const href = `${pathname}${params.size ? `?${params.toString()}` : ""}`;
    if (optionsValue?.push) router.push(href, { scroll: false });
    else router.replace(href, { scroll: false });
  }, [pathname, router, searchKey]);

  useEffect(() => setSearchInput(state.search), [state.search]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = searchInput.trim();
      if (value !== state.search) updateUrl({ search: value });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput, state.search, updateUrl]);

  useEffect(() => setSelectedIds(new Set()), [listQuery]);

  useEffect(() => {
    const pageData = listRequest.data;
    if (!pageData || state.page >= pageData.total_pages) return;
    const nextQuery = buildOpportunityApiQuery({ ...state, page: state.page + 1 }, { now: temporalAnchor });
    void prefetchApiQuery<OpportunityPage>({
      key: queryKeys.opportunities.list(nextQuery),
      path: `/opportunities?${nextQuery}`,
      ...cachePolicy.operational,
    }).catch(() => undefined);
  }, [listRequest.data, state, temporalAnchor]);

  useEffect(() => {
    if (!loading && totalPages > 0 && state.page > totalPages) {
      updateUrl({ page: totalPages }, { resetPage: false });
    }
  }, [loading, state.page, totalPages, updateUrl]);

  const selected = useMemo(() => findings.filter((finding) => selectedIds.has(finding.id)), [findings, selectedIds]);
  const allSelected = !isHistory && findings.length > 0 && selected.length === findings.length;

  const pageSavings = findings.reduce<Record<string, number>>((totals, finding) => {
    if (finding.rule_key === "cost_growth_anomaly") return totals;
    const amount = numericValue(finding.estimated_monthly_savings);
    const currency = finding.currency?.trim();
    if (amount == null || !currency) return totals;
    totals[currency] = (totals[currency] || 0) + amount;
    return totals;
  }, {});
  const pageSavingsEntries = Object.entries(pageSavings).sort(([left], [right]) => left.localeCompare(right));

  const newestObservation = findings.reduce<string | null>((latest, finding) => {
    if (!latest || new Date(finding.last_seen_at) > new Date(latest)) return finding.last_seen_at;
    return latest;
  }, null);
  const newestArchive = findings.reduce<string | null>((latest, finding) => {
    if (!finding.archived_at) return latest;
    if (!latest || new Date(finding.archived_at) > new Date(latest)) return finding.archived_at;
    return latest;
  }, null);

  const currentAccount = options.accounts.find((account) => account.provider === state.provider && account.account_id === state.accountId)
    ?? options.accounts.find((account) => account.account_id === state.accountId);
  const accountOptions = options.accounts
    .filter((account) => !state.provider || account.provider === state.provider)
    .map((account) => ({
      value: account.account_id,
      label: account.account_name || account.account_id,
      accountId: account.account_id,
      provider: providerLabel(account.provider),
      searchTerms: [account.account_name || "", account.account_id, account.provider],
    }));
  if (state.accountId && !accountOptions.some((account) => account.value === state.accountId)) {
    accountOptions.push({
      value: state.accountId,
      label: currentAccount?.account_name || state.accountId,
      accountId: state.accountId,
      provider: currentAccount ? providerLabel(currentAccount.provider) : providerLabel(state.provider),
      searchTerms: [state.accountId],
    });
  }

  const providerOptions = Array.from(new Set([
    ...options.providers.map((provider) => provider.toLowerCase()),
    ...(!isHistory ? collectionRuns.map((run) => run.provider.toLowerCase()) : []),
    ...(state.provider ? [state.provider.toLowerCase()] : []),
  ])).sort().map((provider) => ({ value: provider, label: providerLabel(provider) }));

  const visibleCollectionRuns = collectionRuns.filter((run) =>
    (!state.provider || run.provider.toLowerCase() === state.provider.toLowerCase()) &&
    (!state.accountId || run.account_id === state.accountId),
  );
  const collectionRunOptions = visibleCollectionRuns.map((run) => {
    const account = options.accounts.find((item) => item.provider.toLowerCase() === run.provider.toLowerCase() && item.account_id === run.account_id);
    return {
      value: run.id,
      label: `${formatDate(run.started_at)} · ${providerLabel(run.provider)} · ${formatAccountLabel(account?.account_name, run.account_id)} · ${run.status}`,
    };
  });
  if (state.collectionRunId && !collectionRunOptions.some((item) => item.value === state.collectionRunId)) {
    collectionRunOptions.unshift({ value: state.collectionRunId, label: `Coleta selecionada · ${state.collectionRunId.slice(0, 8)}` });
  }

  const hasFilters = Boolean(
    state.provider || state.accountId || state.region || state.service || state.resourceType ||
    state.severity || state.rule || state.collectionRunId || state.firstSeenCollectionRunId ||
    state.discoveryType || state.resourceId || state.search || state.temporalPreset || state.current ||
    (isHistory && (state.status || state.presenceStatus || state.archivedFrom || state.archivedTo || state.archiveReason)),
  );
  const temporalLabel = state.temporalPreset
    ? `${state.dateField === "last_seen" ? "Última detecção" : "Primeira identificação"}: ${temporalPresetLabels[state.temporalPreset] || state.temporalPreset}${state.temporalPreset === "custom" ? ` · ${state.temporalFrom || "…"} → ${state.temporalTo || "…"}` : ""}`
    : "";
  const activeFilters = [
    state.provider ? `Cloud: ${providerLabel(state.provider)}` : "",
    state.accountId ? `Conta: ${formatAccountLabel(currentAccount?.account_name, state.accountId)}` : "",
    isHistory && state.status ? `Status: ${statusLabel(state.status)}` : "",
    isHistory && state.presenceStatus ? `Presença: ${statusLabel(state.presenceStatus)}` : "",
    state.severity ? `Severidade: ${humanize(state.severity)}` : "",
    state.region ? `Região: ${state.region}` : "",
    state.service ? `Serviço: ${state.service}` : "",
    state.resourceType ? `Tipo: ${state.resourceType}` : "",
    state.rule ? `Regra: ${state.rule}` : "",
    state.search ? `Busca: ${state.search}` : "",
    temporalLabel,
    state.collectionRunId ? `Coleta: ${state.collectionRunId.slice(0, 8)}` : "",
    state.collectionRunId && state.discoveryType ? `Tipo na coleta: ${discoveryTypeLabels[state.discoveryType] || state.discoveryType}` : "",
    state.firstSeenCollectionRunId ? `Primeira coleta: ${state.firstSeenCollectionRunId.slice(0, 8)}` : "",
    state.current ? "Escopo: estado atual" : "",
    isHistory && state.archivedFrom ? `Arquivada desde: ${state.archivedFrom}` : "",
    isHistory && state.archivedTo ? `Arquivada até: ${state.archivedTo}` : "",
    isHistory && state.archiveReason ? `Arquivamento: ${archiveReasonLabels[state.archiveReason]}` : "",
  ].filter(Boolean);

  const archiveFilters = isHistory ? {} : {
    ...(hasFilters && state.status ? { status: state.status } : {}),
    ...(state.provider ? { provider: state.provider } : {}),
    ...(state.accountId ? { account_id: state.accountId } : {}),
    ...(state.region ? { region: state.region } : {}),
    ...(state.service ? { service: state.service } : {}),
    ...(state.resourceType ? { resource_type: state.resourceType } : {}),
    ...(state.severity ? { severity: state.severity } : {}),
    ...(state.rule ? { rule: state.rule } : {}),
    ...(state.collectionRunId ? { collection_run_id: state.collectionRunId } : {}),
    ...(state.resourceId ? { resource_id: state.resourceId } : {}),
    ...(state.search ? { search: state.search } : {}),
    ...(state.current ? { current: true } : {}),
  };
  const archiveFilterLabels = hasFilters ? [state.status ? `Status: ${statusLabel(state.status)}` : "", ...activeFilters].filter(Boolean) : [];
  const archiveScopeMatchesVisibleQuery = !state.temporalPreset && !state.discoveryType && !state.firstSeenCollectionRunId;

  function changeStatus(status: "open" | "treated" | "rejected") {
    setSelectedIds(new Set());
    updateUrl({
      view: null,
      status,
      presence_status: null,
      archived_from: null,
      archived_to: null,
      archive_reason: null,
      sort: "last_seen_at",
      order: "desc",
    });
  }

  function openHistory() {
    setSelectedIds(new Set());
    updateUrl({ view: "history", status: null, current: null, sort: "archived_at", order: "desc" });
  }

  function clearFilters() {
    setSearchInput("");
    updateUrl({
      provider: null,
      account_id: null,
      region: null,
      service: null,
      resource_type: null,
      severity: null,
      rule: null,
      rule_key: null,
      collection_run_id: null,
      first_seen_collection_run_id: null,
      discovery_type: null,
      resource_id: null,
      search: null,
      identified_preset: null,
      date_field: null,
      first_seen_from: null,
      first_seen_to: null,
      last_seen_from: null,
      last_seen_to: null,
      current: null,
      ...(isHistory ? { status: null, presence_status: null, archived_from: null, archived_to: null, archive_reason: null } : {}),
    });
  }

  function changeTemporalField(nextField: "first_seen" | "last_seen") {
    const patch: Record<string, string | null> = {
      date_field: nextField === "first_seen" ? null : nextField,
      first_seen_from: null,
      first_seen_to: null,
      last_seen_from: null,
      last_seen_to: null,
    };
    if (state.temporalPreset === "custom") {
      patch[`${nextField}_from`] = state.temporalFrom || null;
      patch[`${nextField}_to`] = state.temporalTo || null;
    }
    updateUrl(patch);
  }

  function changeTemporalPreset(preset: string) {
    updateUrl({
      identified_preset: preset || null,
      first_seen_from: preset === "custom" && state.dateField === "first_seen" ? state.temporalFrom || null : null,
      first_seen_to: preset === "custom" && state.dateField === "first_seen" ? state.temporalTo || null : null,
      last_seen_from: preset === "custom" && state.dateField === "last_seen" ? state.temporalFrom || null : null,
      last_seen_to: preset === "custom" && state.dateField === "last_seen" ? state.temporalTo || null : null,
    });
  }

  function toggleSelection(id: string) {
    if (isHistory) return;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function openDetail(id: string) {
    updateUrl({ opportunity_id: id }, { resetPage: false, push: true });
  }

  function closeDetail() {
    updateUrl({ opportunity_id: null }, { resetPage: false });
  }

  function openDecision(action: OpportunityDecisionAction, ids: string[], bulk: boolean) {
    if (isHistory) return;
    setDecisionError("");
    setDecision({ action, ids, bulk });
  }

  async function submitDecision(payload: { reason?: string; note?: string }) {
    if (!decision || decisionSaving) return;
    setDecisionSaving(true);
    setDecisionError("");
    setMessage("");
    try {
      const request = buildLifecycleRequest({
        action: decision.action,
        opportunityIds: decision.ids,
        reason: payload.reason,
        note: payload.note,
        bulk: decision.bulk,
      });
      const result = await api<{ updated?: number } | Finding>(request.path, { method: "POST", body: JSON.stringify(request.body) });
      const updated = "updated" in result && typeof result.updated === "number" ? result.updated : 1;
      setMessage(`${updated} oportunidade(s) atualizada(s) com sucesso.`);
      setSelectedIds(new Set());
      setDecision(null);
      if (!decision.bulk && state.opportunityId) closeDetail();
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.dashboard.all);
    } catch (err) {
      setDecisionError(err instanceof Error ? err.message : rejectionFallback);
    } finally {
      setDecisionSaving(false);
    }
  }

  function archiveSucceeded(feedback: string) {
    setMessage(feedback);
    setSelectedIds(new Set());
    setArchiveDialog(null);
    if (state.opportunityId) closeDetail();
    invalidateApiQueries(queryKeys.opportunities.all);
    invalidateApiQueries(queryKeys.dashboard.all);
    invalidateApiQueries(["opportunity-history"]);
  }

  async function restoreHistoryRow(finding: HistoricalFinding) {
    if (!finding.archived || unarchiveSavingId) return;
    const isRejected = finding.status === "rejected";
    setUnarchiveSavingId(finding.id);
    setMessage("");
    try {
      if (isRejected) {
        await api(`/opportunities/${finding.id}/reopen`, { method: "POST", body: JSON.stringify({}) });
        setMessage("Oportunidade reaberta e devolvida ao backlog operacional.");
      } else {
        await api(`/opportunities/${finding.id}/unarchive`, { method: "POST" });
        setMessage("Oportunidade desarquivada com sucesso.");
      }
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.dashboard.all);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : isRejected ? "Não foi possível reabrir a oportunidade." : "Não foi possível desarquivar a oportunidade.");
    } finally {
      setUnarchiveSavingId("");
    }
  }

  function recommendationActions(finding: HistoricalFinding): ReactNode {
    if (isHistory) {
      return (
        <div className={styles.rowActions}>
          <Button variant="ghost" size="sm" onClick={() => openDetail(finding.id)}>Ver detalhes</Button>
          <Button variant="outline" size="sm" loading={unarchiveSavingId === finding.id} onClick={() => void restoreHistoryRow(finding)}>
            {finding.status === "rejected" ? "Reabrir oportunidade" : "Desarquivar"}
          </Button>
        </div>
      );
    }
    if (finding.status === "open") {
      return (
        <div className={styles.rowActions}>
          <Button variant="ghost" size="sm" onClick={() => openDetail(finding.id)}>Ver detalhes</Button>
          <Button variant="outline" size="sm" onClick={() => openDecision("treat", [finding.id], false)}>Tratar</Button>
          <Button variant="danger" size="sm" onClick={() => openDecision("reject", [finding.id], false)}>Rejeitar</Button>
          <Button variant="ghost" size="sm" onClick={() => setArchiveDialog({ mode: "individual", opportunityId: finding.id })}>Arquivar</Button>
        </div>
      );
    }
    return (
      <div className={styles.rowActions}>
        <Button variant="ghost" size="sm" onClick={() => openDetail(finding.id)}>Ver detalhes</Button>
        <Button variant="outline" size="sm" onClick={() => openDecision("reopen", [finding.id], false)}>Reabrir</Button>
        <Button variant="ghost" size="sm" onClick={() => setArchiveDialog({ mode: "individual", opportunityId: finding.id })}>Arquivar</Button>
      </div>
    );
  }

  const sortOptions = isHistory ? historySortOptions : operationalSortOptions;
  const useCards = !isHistory && !listRequest.isLoading && !listError && findings.length > 0 && total <= 6;

  return (
    <div className={styles.page}>
      <PageHeader
        title="Recomendações"
        description="Priorize oportunidades de otimização por impacto, economia potencial, confiança e contexto do recurso."
        actions={(
          <Button
            variant="outline"
            leadingIcon={<RefreshCw {...iconDefaults} />}
            loading={listRequest.isFetching || statsRequest.isFetching || optionsRequest.isFetching}
            onClick={() => { void listRequest.refetch(); void statsRequest.refetch(); void optionsRequest.refetch(); }}
          >
            Atualizar
          </Button>
        )}
      />

      {message ? <Alert variant="info" title="Atualização de recomendações" description={message} /> : null}
      {filterError ? <Alert variant="warning" title="Algumas opções de filtro estão indisponíveis" description={filterError} /> : null}

      <Section title="Resumo" description="Contagens respeitam o escopo atual. Economia potencial abaixo representa somente os itens carregados nesta página.">
        <div className={styles.metricsGrid} aria-label="Resumo das recomendações">
          <MetricCard
            label="Oportunidades na visão"
            value={loading && !listRequest.data ? "—" : total}
            supportingText={isHistory ? "Registros arquivados no escopo atual" : `${statusLabel(state.status || "open")} após os filtros aplicados`}
            icon={<WalletCards {...iconDefaults} />}
            loading={listRequest.isLoading}
          />
          <MetricCard
            label="Economia potencial na página"
            value={pageSavingsEntries.length ? (
              <span className={styles.savingsStack}>
                {pageSavingsEntries.map(([currency, amount]) => (
                  <span key={currency}><CurrencyDisplay value={amount} currency={currency} locale="pt-BR" maximumFractionDigits={2} /> <span>/mês</span></span>
                ))}
              </span>
            ) : "—"}
            supportingText="Moedas preservadas separadamente; nenhuma conversão FX é aplicada"
            icon={<WalletCards {...iconDefaults} />}
            loading={listRequest.isLoading}
          />
          <MetricCard
            label={isHistory ? "Arquivamento mais recente" : "Última detecção na página"}
            value={formatDate(isHistory ? newestArchive : newestObservation)}
            supportingText={isHistory ? "Data de entrada no histórico entre os itens carregados" : "Timestamp persistido; não representa dados em tempo real"}
            icon={isHistory ? <Archive {...iconDefaults} /> : <CalendarClock {...iconDefaults} />}
            loading={listRequest.isLoading}
          />
        </div>
      </Section>

      <Tabs
        value={isHistory ? "history" : state.status || "open"}
        defaultValue="open"
        onValueChange={(value) => { if (value === "history") openHistory(); else changeStatus(value as "open" | "treated" | "rejected"); }}
      >
        <TabsList aria-label="Estado das recomendações">
          {statusTabs.map((tab) => <TabsTrigger key={tab.value} value={tab.value}>{tab.label} · {statsLoading ? "…" : stats[tab.value]}</TabsTrigger>)}
          <TabsTrigger value="history">Histórico{isHistory ? ` · ${loading ? "…" : total}` : ""}</TabsTrigger>
        </TabsList>
      </Tabs>

      <FilterBar
        aria-label="Filtros de recomendações"
        clearAction={hasFilters ? <Button variant="ghost" size="sm" onClick={clearFilters}>Limpar filtros</Button> : undefined}
      >
        <Input label="Busca" value={searchInput} placeholder="Recurso, ID, título, regra ou serviço" leadingIcon={<Search {...iconDefaults} />} onChange={(event) => setSearchInput(event.target.value)} />
        <ProviderSelector
          label="Provider"
          value={state.provider}
          onChange={(provider) => updateUrl({ provider, account_id: null, collection_run_id: null, discovery_type: null })}
          options={providerOptions}
          loading={filtersLoading}
          placeholder="Todos os providers"
          clearLabel="Todos os providers"
          searchable={false}
        />
        <AccountSelector
          label="Conta"
          value={state.accountId}
          onChange={(accountId) => updateUrl({ account_id: accountId, collection_run_id: null, discovery_type: null })}
          options={accountOptions}
          loading={filtersLoading}
          placeholder="Todas as contas autorizadas"
          clearLabel="Todas as contas autorizadas"
          searchable={false}
        />
        <Select label="Serviço" value={state.service} onChange={(event) => updateUrl({ service: event.target.value })} options={activeOption(options.services, state.service).map((value) => ({ value, label: value }))} placeholder="Todos os serviços" />
        <Select label="Tipo de recurso" value={state.resourceType} onChange={(event) => updateUrl({ resource_type: event.target.value })} options={activeOption(options.resource_types, state.resourceType).map((value) => ({ value, label: humanize(value) }))} placeholder="Todos os tipos" />
        <Select label="Impacto / severidade" value={state.severity} onChange={(event) => updateUrl({ severity: event.target.value })} options={[{ value: "high", label: "Alta" }, { value: "medium", label: "Média" }, { value: "low", label: "Baixa" }]} placeholder="Todas" />
        <Select label="Regra" value={state.rule} onChange={(event) => updateUrl({ rule: event.target.value, rule_key: null })} options={activeOption(options.rules, state.rule).map((value) => ({ value, label: value }))} placeholder="Todas as regras" />
      </FilterBar>

      {activeFilters.length > 0 ? <div className={styles.activeFilters} aria-label="Filtros ativos">{activeFilters.map((label) => <Badge key={label} variant="neutral">{label}</Badge>)}</div> : null}

      <details className={styles.advancedFilters}>
        <summary>Filtros avançados e contexto de coleta</summary>
        <div className={styles.advancedGrid}>
          <Select label="Região" value={state.region} onChange={(event) => updateUrl({ region: event.target.value })} options={activeOption(options.regions, state.region).map((value) => ({ value, label: value }))} placeholder="Todas as regiões" />
          <Select label="Filtrar data por" value={state.dateField} onChange={(event) => changeTemporalField(event.target.value as "first_seen" | "last_seen")} options={[{ value: "first_seen", label: "Primeira identificação" }, { value: "last_seen", label: "Última detecção" }]} />
          <Select label="Período" value={state.temporalPreset} onChange={(event) => changeTemporalPreset(event.target.value)} options={[{ value: "today", label: "Hoje" }, { value: "last_24h", label: "Últimas 24h" }, { value: "last_7d", label: "Últimos 7 dias" }, { value: "last_30d", label: "Últimos 30 dias" }, { value: "custom", label: "Personalizado" }]} placeholder="Todo o período" />
          {state.temporalPreset === "custom" ? <><Input type="date" label="De" value={state.temporalFrom} onChange={(event) => updateUrl({ [`${state.dateField}_from`]: event.target.value })} /><Input type="date" label="Até" value={state.temporalTo} onChange={(event) => updateUrl({ [`${state.dateField}_to`]: event.target.value })} /></> : null}
          <Select label="Coleta" value={state.collectionRunId} onChange={(event) => updateUrl({ collection_run_id: event.target.value, discovery_type: event.target.value ? (state.discoveryType || "observed") : null })} options={collectionRunOptions} placeholder="Todas as coletas" />
          {state.collectionRunId ? <Select label="Tipo na coleta" value={state.discoveryType || "observed"} onChange={(event) => updateUrl({ discovery_type: event.target.value })} options={Object.entries(discoveryTypeLabels).map(([value, label]) => ({ value, label }))} /> : null}
          {!isHistory ? (
            <Checkbox checked={state.current} label="Somente estado atual" description="Usa o contrato current=true já existente no backend." onChange={(event) => updateUrl({ current: event.target.checked ? "true" : null })} />
          ) : (
            <>
              <Select label="Status humano" value={state.status} onChange={(event) => updateUrl({ status: event.target.value })} options={statusTabs.map((tab) => ({ value: tab.value, label: statusLabel(tab.value) }))} placeholder="Todos" />
              <Select label="Presença técnica" value={state.presenceStatus} onChange={(event) => updateUrl({ presence_status: event.target.value })} options={[{ value: "active", label: "Ativa" }, { value: "missing", label: "Ausente" }, { value: "resolved_externally", label: "Resolvida externamente" }]} placeholder="Todas" />
              <Input type="date" label="Arquivada desde" value={state.archivedFrom} onChange={(event) => updateUrl({ archived_from: event.target.value })} />
              <Input type="date" label="Arquivada até" value={state.archivedTo} onChange={(event) => updateUrl({ archived_to: event.target.value })} />
              <Select label="Motivo do arquivamento" value={state.archiveReason} onChange={(event) => updateUrl({ archive_reason: event.target.value })} options={Object.entries(archiveReasonLabels).map(([value, label]) => ({ value, label }))} placeholder="Todos" />
            </>
          )}
        </div>
      </details>

      <Section
        title={isHistory ? "Histórico de recomendações" : "Oportunidades"}
        description={useCards ? "Oportunidades curadas em formato compacto, priorizando impacto, economia potencial, confiança, recurso e ação." : "Lista densa para comparar recomendações em volume sem perder contexto financeiro e técnico."}
        actions={(
          <div className={styles.sortControls}>
            <Select label="Ordenar por" value={state.sort} onChange={(event) => updateUrl({ sort: event.target.value })} options={sortOptions} />
            <Select label="Ordem" value={state.order} onChange={(event) => updateUrl({ order: event.target.value })} options={[{ value: "desc", label: "Decrescente" }, { value: "asc", label: "Crescente" }]} />
          </div>
        )}
      >
        <div className={styles.workspaceMeta}>
          <span>{listRequest.data ? `${total} resultado(s)` : "Contagem indisponível"}</span>
          {listRequest.isFetching && !listRequest.isLoading ? <StatusIndicator status="pending" label="Atualizando" /> : null}
        </div>

        {!isHistory ? (
          <div className={styles.selectionBar}>
            <Checkbox checked={allSelected} indeterminate={selected.length > 0 && !allSelected} disabled={loading || !findings.length} label="Selecionar página atual" onChange={() => setSelectedIds(allSelected ? new Set() : new Set(findings.map((finding) => finding.id)))} />
            <span>{selected.length} selecionada(s)</span>
            {selected.length > 0 ? (
              <div className={styles.bulkActions} aria-label="Ações em massa">
                <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>Limpar seleção</Button>
                {state.status === "open" ? <><Button variant="outline" size="sm" onClick={() => openDecision("treat", selected.map((item) => item.id), true)}>Marcar como tratadas</Button><Button variant="danger" size="sm" onClick={() => openDecision("reject", selected.map((item) => item.id), true)}>Rejeitar</Button></> : <Button variant="outline" size="sm" onClick={() => openDecision("reopen", selected.map((item) => item.id), true)}>Reabrir</Button>}
                <Button variant="ghost" size="sm" onClick={() => setArchiveDialog({ mode: "selected", opportunityIds: selected.map((item) => item.id) })}>Arquivar selecionadas</Button>
              </div>
            ) : total > 0 && archiveScopeMatchesVisibleQuery ? (
              <div className={styles.bulkActions} aria-label="Arquivamento do escopo">
                <Button variant="ghost" size="sm" onClick={() => setArchiveDialog({ mode: "filter" })}>{hasFilters ? "Arquivar todas deste filtro" : "Arquivar todo o backlog"}</Button>
                <Button variant="ghost" size="sm" onClick={() => setArchiveDialog({ mode: "period" })}>Fechar período</Button>
              </div>
            ) : null}
          </div>
        ) : <Alert variant="info" title="Consulta histórica" description="Ações operacionais em massa ficam desabilitadas no histórico; restauração permanece disponível por registro." />}

        {listError ? <Alert variant="danger" title="Não foi possível carregar as recomendações" description={listError} actions={<Button variant="outline" size="sm" onClick={() => void listRequest.refetch()}>Tentar novamente</Button>} /> : null}

        {listRequest.isLoading ? (
          <div className={styles.cardsGrid} aria-hidden="true"><Skeleton /><Skeleton /><Skeleton /></div>
        ) : !listError && findings.length === 0 ? (
          <DataState
            empty
            emptyTitle={isHistory ? (hasFilters ? "Nenhum registro histórico corresponde aos filtros" : "Nenhuma recomendação arquivada") : (hasFilters ? "Nenhuma oportunidade corresponde aos filtros" : `Nenhuma oportunidade ${statusLabel(state.status || "open").toLowerCase()} encontrada`)}
            emptyDescription={hasFilters ? "Ajuste ou limpe os filtros para ampliar o escopo." : "A engine não retornou recomendações nesse estado para as coletas disponíveis."}
            emptyAction={hasFilters ? <Button variant="outline" onClick={clearFilters}>Limpar filtros</Button> : undefined}
          ><span /></DataState>
        ) : useCards ? (
          <div className={styles.cardsGrid}>
            {findings.map((finding) => (
              <RecommendationCard
                key={finding.id}
                title={finding.title}
                description={finding.description}
                provider={finding.provider}
                status={statusTone(finding.status)}
                statusLabel={statusLabel(finding.status)}
                potentialSavings={<SavingsValue finding={finding} />}
                impact={<StatusIndicator status={severityTone(finding.severity)} label={humanize(finding.severity)} />}
                confidence={finding.confidence ? <StatusIndicator status={confidenceTone(finding.confidence)} label={humanize(finding.confidence)} /> : "—"}
                resource={<ResourceIdentifier primary={finding.resource_name || finding.resource_id} technicalId={finding.resource_name ? finding.resource_id : undefined} copyValue={finding.resource_id} />}
                metadata={<div className={styles.cardMetadata}><span>{formatAccountLabel(finding.account_name, finding.account_id)}</span><span>{finding.region || "Sem região"}</span><span>{finding.service || "Sem serviço"}</span>{finding.resource_type ? <span>{humanize(finding.resource_type)}</span> : null}<span>Última detecção: {formatDate(finding.last_seen_at)}</span>{finding.needs_review ? <StatusIndicator status="warning" label="Detectada novamente" /> : null}</div>}
                actions={recommendationActions(finding)}
                onMouseEnter={() => { void prefetchApiQuery({ key: queryKeys.opportunities.detail(finding.id), path: `/opportunities/${finding.id}`, ...cachePolicy.detail }).catch(() => undefined); }}
              />
            ))}
          </div>
        ) : (
          <Table aria-label={isHistory ? "Histórico de recomendações" : "Recomendações"}>
            <TableHeader>
              <TableRow staticRow>
                {!isHistory ? <TableHead>Seleção</TableHead> : null}
                <TableHead>Recomendação</TableHead>
                <TableHead>Recurso / provider</TableHead>
                <TableHead>Conta / região</TableHead>
                <TableHead>Impacto / confiança</TableHead>
                <TableHead numeric>Economia potencial</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Ações</TableHead>
              </TableRow>
            </TableHeader>
            {loading && findings.length === 0 ? <OpportunityLoadingRows history={isHistory} /> : (
              <TableBody>
                {findings.map((finding) => (
                  <TableRow key={finding.id} selected={selectedIds.has(finding.id)} onMouseEnter={() => { void prefetchApiQuery({ key: queryKeys.opportunities.detail(finding.id), path: `/opportunities/${finding.id}`, ...cachePolicy.detail }).catch(() => undefined); }}>
                    {!isHistory ? <TableCell><Checkbox checked={selectedIds.has(finding.id)} aria-label={`Selecionar ${finding.title} · ${finding.resource_id}`} onChange={() => toggleSelection(finding.id)} /></TableCell> : null}
                    <TableCell><Button variant="ghost" size="sm" onClick={() => openDetail(finding.id)}>{finding.title}</Button><span className={styles.secondary}>{finding.rule_key}</span><span className={styles.secondary}>{finding.description}</span></TableCell>
                    <TableCell><div className={styles.resourceCell}><ResourceIdentifier primary={finding.resource_name || finding.resource_id} technicalId={finding.resource_name ? finding.resource_id : undefined} copyValue={finding.resource_id} /><ProviderBadge provider={finding.provider} /></div></TableCell>
                    <TableCell>{formatAccountLabel(finding.account_name, finding.account_id)}<span className={styles.secondary}>{finding.region || "Sem região"} · {finding.service || "Sem serviço"}</span>{finding.resource_type ? <span className={styles.secondary}>{humanize(finding.resource_type)}</span> : null}</TableCell>
                    <TableCell><div className={styles.statusStack}><StatusIndicator status={severityTone(finding.severity)} label={`Impacto: ${humanize(finding.severity)}`} /><StatusIndicator status={confidenceTone(finding.confidence)} label={`Confiança: ${finding.confidence ? humanize(finding.confidence) : "—"}`} /></div></TableCell>
                    <TableCell numeric><SavingsValue finding={finding} /><span className={styles.secondary}>Custo atual: <MoneyValue value={finding.current_monthly_cost} currency={finding.currency} /></span></TableCell>
                    <TableCell><div className={styles.statusStack}><StatusIndicator status={statusTone(finding.status)} label={statusLabel(finding.status)} />{isHistory ? <StatusIndicator status={statusTone(finding.presence_status)} label={statusLabel(finding.presence_status)} /> : null}{finding.needs_review ? <StatusIndicator status="warning" label="Detectada novamente" /> : null}</div><span className={styles.secondary}>{isHistory ? `Arquivada: ${formatDate(finding.archived_at)}` : `Última detecção: ${formatDate(finding.last_seen_at)}`}</span></TableCell>
                    <TableCell>{recommendationActions(finding)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            )}
          </Table>
        )}

        {listRequest.data ? (
          <div className={styles.paginationRow}>
            <Select label="Itens por página" value={String(state.pageSize)} onChange={(event) => updateUrl({ page_size: event.target.value })} options={[{ value: "25", label: "25" }, { value: "50", label: "50" }, { value: "100", label: "100" }]} />
            {totalPages > 1 ? <Pagination page={state.page} pageCount={totalPages} onPageChange={(page) => updateUrl({ page }, { resetPage: false })} /> : null}
          </div>
        ) : null}
      </Section>

      {state.opportunityId ? <OpportunityDetail opportunityId={state.opportunityId} onClose={closeDetail} onAction={(action, id) => openDecision(action, [id], false)} onArchive={(id) => setArchiveDialog({ mode: "individual", opportunityId: id })} /> : null}
      {decision ? <OpportunityDecisionDialog action={decision.action} count={decision.ids.length} saving={decisionSaving} error={decisionError} onClose={() => { if (!decisionSaving) { setDecision(null); setDecisionError(""); } }} onSubmit={submitDecision} /> : null}
      {archiveDialog ? <OpportunityArchiveDialog mode={archiveDialog.mode} opportunityId={archiveDialog.opportunityId} opportunityIds={archiveDialog.opportunityIds} filters={archiveFilters} filterLabels={archiveFilterLabels} onClose={() => setArchiveDialog(null)} onSuccess={archiveSucceeded} /> : null}
    </div>
  );
}
