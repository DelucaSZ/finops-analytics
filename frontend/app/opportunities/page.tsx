"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Building2,
  ChevronLeft,
  ChevronRight,
  Cloud,
  Filter,
  ListFilter,
  RefreshCw,
  Search,
  Tags,
  WalletCards,
  X,
} from "lucide-react";
import { OpportunityDecisionDialog } from "@/components/opportunity-decision-dialog";
import type { OpportunityDecisionAction } from "@/components/opportunity-decision-dialog";
import { OpportunityDetail } from "@/components/opportunity-detail";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate, usd } from "@/lib/api";
import {
  buildLifecycleRequest,
  buildOpportunityApiQuery,
  buildOpportunityStatsQuery,
  parseOpportunitySearchParams,
  patchOpportunityUrl,
} from "@/lib/opportunity-query.mjs";
import type { OpportunityQueryState } from "@/lib/opportunity-query.mjs";
import type {
  AwsAccount,
  CollectionRun,
  Finding,
  OpportunityPage,
  OpportunityStats,
  Policy,
} from "@/lib/types";

const statusTabs = [
  { value: "open", label: "Abertas" },
  { value: "treated", label: "Tratadas" },
  { value: "rejected", label: "Rejeitadas" },
] as const;

const rejectionFallback = "Não foi possível atualizar a oportunidade. Nenhuma alteração foi aplicada.";

const sortOptions = [
  ["last_seen_at", "Última detecção"],
  ["first_seen_at", "Primeira detecção"],
  ["severity", "Severidade"],
  ["estimated_savings", "Impacto financeiro"],
  ["created_at", "Criação"],
] as const;

function pageWindow(page: number, totalPages: number) {
  if (totalPages <= 1) return totalPages ? [1] : [];
  const start = Math.max(1, Math.min(page - 2, totalPages - 4));
  const end = Math.min(totalPages, start + 4);
  return Array.from({ length: end - start + 1 }, (_, index) => start + index);
}

function savingsLabel(finding: Finding) {
  return finding.rule_key === "cost_growth_anomaly"
    ? "Não estimada"
    : `${usd(finding.estimated_monthly_savings)}/mês`;
}

function SkeletonRows() {
  return (
    <tbody aria-hidden="true">
      {Array.from({ length: 6 }, (_, index) => (
        <tr key={index} className="opportunity-skeleton-row">
          <td><span className="skeleton-box skeleton-check" /></td>
          <td><span className="skeleton-box skeleton-title" /><span className="skeleton-box skeleton-line" /></td>
          <td><span className="skeleton-box skeleton-line" /><span className="skeleton-box skeleton-line short" /></td>
          <td><span className="skeleton-box skeleton-pill" /></td>
          <td><span className="skeleton-box skeleton-line short" /></td>
          <td><span className="skeleton-box skeleton-line" /></td>
          <td><span className="skeleton-box skeleton-pill" /></td>
        </tr>
      ))}
    </tbody>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<div className="opportunities-boot" role="status">Carregando oportunidades…</div>}>
      <OpportunitiesContent />
    </Suspense>
  );
}

function OpportunitiesContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<OpportunityQueryState>(
    () => parseOpportunitySearchParams(searchKey),
    [searchKey],
  );
  const listQuery = useMemo(() => buildOpportunityApiQuery(state), [
    state.accountId, state.collectionRunId, state.order, state.page, state.pageSize,
    state.provider, state.region, state.resourceId, state.rule, state.search,
    state.severity, state.sort, state.status,
  ]);
  const statsQuery = useMemo(() => buildOpportunityStatsQuery(state), [
    state.accountId, state.collectionRunId, state.provider, state.region,
    state.resourceId, state.rule, state.search, state.severity,
  ]);

  const [findings, setFindings] = useState<Finding[]>([]);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [collectionRuns, setCollectionRuns] = useState<CollectionRun[]>([]);
  const [stats, setStats] = useState<OpportunityStats>({ open: 0, treated: 0, rejected: 0 });
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [filtersLoading, setFiltersLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [message, setMessage] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState(state.search);
  const [regionInput, setRegionInput] = useState(state.region);
  const [accountInput, setAccountInput] = useState(state.accountId);
  const [decision, setDecision] = useState<{
    action: OpportunityDecisionAction;
    ids: string[];
    bulk: boolean;
  } | null>(null);
  const [decisionSaving, setDecisionSaving] = useState(false);
  const [decisionError, setDecisionError] = useState("");
  const selectAllRef = useRef<HTMLInputElement>(null);

  const updateUrl = useCallback((patch: Record<string, string | number | null | undefined>, options?: { resetPage?: boolean; push?: boolean }) => {
    const params = patchOpportunityUrl(searchKey, patch, { resetPage: options?.resetPage });
    const href = `${pathname}${params.size ? `?${params.toString()}` : ""}`;
    if (options?.push) router.push(href, { scroll: false });
    else router.replace(href, { scroll: false });
  }, [pathname, router, searchKey]);

  useEffect(() => setSearchInput(state.search), [state.search]);
  useEffect(() => setRegionInput(state.region), [state.region]);
  useEffect(() => setAccountInput(state.accountId), [state.accountId]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const value = searchInput.trim();
      if (value !== state.search) updateUrl({ search: value });
    }, 350);
    return () => window.clearTimeout(timer);
  }, [searchInput, state.search, updateUrl]);

  useEffect(() => {
    const controller = new AbortController();
    setFiltersLoading(true);
    setFilterError("");
    Promise.all([
      api<AwsAccount[]>("/accounts", { signal: controller.signal }),
      api<Policy[]>("/policies/global", { signal: controller.signal }),
    ])
      .then(([accountData, policyData]) => {
        setAccounts(accountData);
        setPolicies(policyData);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setFilterError(err instanceof Error ? err.message : "Não foi possível carregar as opções de filtro.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setFiltersLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    api<CollectionRun[]>("/collections?limit=100&offset=0", { signal: controller.signal })
      .then(setCollectionRuns)
      .catch(() => {
        if (!controller.signal.aborted) setCollectionRuns([]);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setListError("");
    api<OpportunityPage>(`/opportunities?${listQuery}`, { signal: controller.signal })
      .then((data) => {
        setFindings(data.items);
        setTotal(data.total);
        setTotalPages(data.total_pages);
        setSelectedIds(new Set());
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setListError(err instanceof Error ? err.message : "Não foi possível carregar as oportunidades.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [listQuery, reloadKey]);

  useEffect(() => {
    const controller = new AbortController();
    setStatsLoading(true);
    api<OpportunityStats>(`/opportunities/stats${statsQuery ? `?${statsQuery}` : ""}`, { signal: controller.signal })
      .then(setStats)
      .catch(() => {
        if (!controller.signal.aborted) setStats({ open: 0, treated: 0, rejected: 0 });
      })
      .finally(() => {
        if (!controller.signal.aborted) setStatsLoading(false);
      });
    return () => controller.abort();
  }, [reloadKey, statsQuery]);


  useEffect(() => {
    if (!loading && totalPages > 0 && state.page > totalPages) {
      updateUrl({ page: totalPages }, { resetPage: false });
    }
  }, [loading, state.page, totalPages, updateUrl]);

  const selected = useMemo(
    () => findings.filter((finding) => selectedIds.has(finding.id)),
    [findings, selectedIds],
  );
  const allSelected = findings.length > 0 && selected.length === findings.length;
  const pageSavings = findings.reduce((sum, finding) => sum + Number(finding.estimated_monthly_savings), 0);
  const newestObservation = findings.reduce<string | null>((latest, finding) => {
    if (!latest || new Date(finding.last_seen_at) > new Date(latest)) return finding.last_seen_at;
    return latest;
  }, null);
  const currentAccount = accounts.find((account) => account.aws_account_id === state.accountId);
  const providerOptions = Array.from(new Set([
    "aws",
    ...collectionRuns.map((run) => run.provider.toLowerCase()),
    ...(state.provider ? [state.provider.toLowerCase()] : []),
  ])).sort();
  const visibleCollectionRuns = collectionRuns.filter((run) =>
    (!state.provider || run.provider.toLowerCase() === state.provider.toLowerCase()) &&
    (!state.accountId || run.account_id === state.accountId),
  );
  const pages = pageWindow(state.page, totalPages);
  const hasFilters = Boolean(
    state.provider || state.accountId || state.region || state.severity || state.rule ||
    state.collectionRunId || state.resourceId || state.search,
  );

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selected.length > 0 && !allSelected;
    }
  }, [allSelected, selected.length]);

  function changeStatus(status: "open" | "treated" | "rejected") {
    setSelectedIds(new Set());
    updateUrl({ status });
  }

  function clearFilters() {
    setSearchInput("");
    setRegionInput("");
    setAccountInput("");
    updateUrl({
      provider: null,
      account_id: null,
      region: null,
      severity: null,
      rule: null,
      rule_key: null,
      collection_run_id: null,
      resource_id: null,
      search: null,
    });
  }

  function toggleSelection(id: string) {
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
      const result = await api<{ updated?: number } | Finding>(request.path, {
        method: "POST",
        body: JSON.stringify(request.body),
      });
      const updated = "updated" in result && typeof result.updated === "number" ? result.updated : 1;
      setMessage(`${updated} oportunidade(s) atualizada(s) com sucesso.`);
      setSelectedIds(new Set());
      setDecision(null);
      if (!decision.bulk && state.opportunityId) closeDetail();
      setReloadKey((value) => value + 1);
    } catch (err) {
      setDecisionError(err instanceof Error ? err.message : rejectionFallback);
    } finally {
      setDecisionSaving(false);
    }
  }

  function commitAccountInput() {
    const value = accountInput.trim();
    if (!value) {
      if (state.accountId) updateUrl({ account_id: null });
      return;
    }
    const match = accounts.find((account) => account.aws_account_id === value);
    if (match) {
      if (state.accountId !== value) updateUrl({ account_id: value, collection_run_id: null });
      return;
    }
    setAccountInput(state.accountId);
  }

  return (
    <>
      <PageHeader
        eyebrow="FINOPS OPERACIONAL"
        title="Oportunidades"
        description="Backlog operacional de achados, decisões e histórico por cloud, conta e coleta."
      />

      {message && <div className="alert success opportunity-feedback" role="status">{message}</div>}
      {filterError && <div className="alert error opportunity-feedback" role="alert">{filterError}</div>}

      <nav className="opportunity-tabs" aria-label="Estado das oportunidades">
        {statusTabs.map((tab) => {
          const count = stats[tab.value];
          const active = state.status === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              className={active ? "opportunity-tab active" : "opportunity-tab"}
              aria-current={active ? "page" : undefined}
              onClick={() => changeStatus(tab.value)}
            >
              <span>{tab.label}</span>
              <strong aria-label={`${count} oportunidades`}>{statsLoading ? "…" : count}</strong>
            </button>
          );
        })}
      </nav>

      <section className="panel opportunity-filter-panel" aria-label="Filtros de oportunidades">
        <div className="opportunity-filter-heading">
          <div><ListFilter size={18} /><strong>Filtros</strong><span>Combinados no servidor e persistidos na URL</span></div>
          {hasFilters && <button className="filter-clear" type="button" onClick={clearFilters}><X size={15} /> Limpar filtros</button>}
        </div>
        <div className="opportunity-filter-grid">
          <label className="opportunity-filter search-filter">
            <span>Busca</span>
            <div><Search size={16} /><input value={searchInput} placeholder="Recurso, título, regra ou serviço" onChange={(event) => setSearchInput(event.target.value)} /></div>
          </label>

          <label className="opportunity-filter">
            <span>Cloud</span>
            <div><Cloud size={16} /><select value={state.provider} onChange={(event) => updateUrl({ provider: event.target.value, collection_run_id: null })}>
              <option value="">Todas as clouds</option>
              {providerOptions.map((provider) => <option key={provider} value={provider}>{provider.toUpperCase()}</option>)}
            </select></div>
          </label>

          <label className="opportunity-filter account-filter">
            <span>Conta</span>
            <div><Building2 size={16} /><input
              list="opportunity-account-options"
              value={accountInput}
              placeholder={filtersLoading ? "Carregando contas…" : "Buscar por Account ID"}
              onChange={(event) => {
                const value = event.target.value;
                setAccountInput(value);
                if (!value) updateUrl({ account_id: null, collection_run_id: null });
                else if (accounts.some((account) => account.aws_account_id === value)) {
                  updateUrl({ account_id: value, collection_run_id: null });
                }
              }}
              onBlur={commitAccountInput}
              onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
            /></div>
            {currentAccount && <small>{currentAccount.name} · {currentAccount.aws_account_id}</small>}
            <datalist id="opportunity-account-options">
              {accounts.map((account) => <option key={account.id} value={account.aws_account_id}>{account.name} · {account.aws_account_id}</option>)}
            </datalist>
          </label>

          <label className="opportunity-filter">
            <span>Região</span>
            <div><Filter size={16} /><input
              value={regionInput}
              placeholder="Ex.: us-east-1"
              onChange={(event) => setRegionInput(event.target.value)}
              onBlur={() => { if (regionInput.trim() !== state.region) updateUrl({ region: regionInput.trim() }); }}
              onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
            /></div>
          </label>

          <label className="opportunity-filter">
            <span>Severidade</span>
            <div><Filter size={16} /><select value={state.severity} onChange={(event) => updateUrl({ severity: event.target.value })}>
              <option value="">Todas</option>
              <option value="high">Alta</option>
              <option value="medium">Média</option>
              <option value="low">Baixa</option>
            </select></div>
          </label>

          <label className="opportunity-filter">
            <span>Regra / Analyzer</span>
            <div><Tags size={16} /><select value={state.rule} onChange={(event) => updateUrl({ rule: event.target.value, rule_key: null })}>
              <option value="">Todas as regras</option>
              {policies
                .map((policy) => [policy.rule_key, policy.name] as const)
                .sort((a, b) => a[1].localeCompare(b[1], "pt-BR"))
                .map(([key, name]) => <option key={key} value={key}>{name}</option>)}
            </select></div>
          </label>

          <label className="opportunity-filter collection-filter">
            <span>CollectionRun</span>
            <div><RefreshCw size={16} /><select value={state.collectionRunId} onChange={(event) => updateUrl({ collection_run_id: event.target.value })}>
              <option value="">Todas as coletas</option>
              {state.collectionRunId && !visibleCollectionRuns.some((run) => run.id === state.collectionRunId) && (
                <option value={state.collectionRunId}>Coleta selecionada · {state.collectionRunId.slice(0, 8)}</option>
              )}
              {visibleCollectionRuns.map((run) => (
                <option key={run.id} value={run.id}>
                  {formatDate(run.started_at)} · {run.provider.toUpperCase()} · {run.account_id} · {run.status}
                </option>
              ))}
            </select></div>
          </label>
        </div>
      </section>

      <section className="opportunity-summary-grid" aria-label="Resumo da visão atual">
        <div className="opportunity-summary-card">
          <span>Resultados nesta visão</span>
          <strong>{loading && !findings.length ? "…" : total}</strong>
          <small>{state.status === "open" ? "Abertas" : state.status === "treated" ? "Tratadas" : "Rejeitadas"}</small>
        </div>
        <div className="opportunity-summary-card">
          <WalletCards size={18} />
          <span>Economia na página</span>
          <strong>{usd(pageSavings)}/mês</strong>
          <small>Somente os {findings.length} itens carregados</small>
        </div>
        <div className="opportunity-summary-card">
          <span>Dados da coleta</span>
          <strong className="summary-date">{newestObservation ? formatDate(newestObservation) : "—"}</strong>
          <small>Última detecção nesta página; não é tempo real</small>
        </div>
      </section>

      <section className="panel opportunity-workspace" aria-busy={loading}>
        <div className="opportunity-workspace-toolbar">
          <div className="selection-summary">
            <label className="selection-control">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                disabled={loading || !findings.length}
                onChange={() => setSelectedIds(allSelected ? new Set() : new Set(findings.map((finding) => finding.id)))}
              />
              Selecionar página atual
            </label>
            <span>{selected.length} selecionada(s)</span>
          </div>

          {selected.length > 0 && (
            <div className="bulk-actions opportunity-bulk-actions" aria-label="Ações em massa">
              <button className="button ghost" type="button" onClick={() => setSelectedIds(new Set())}>Limpar seleção</button>
              {state.status === "open" ? (
                <>
                  <button className="button ghost" type="button" onClick={() => openDecision("treat", selected.map((item) => item.id), true)}>Marcar como tratadas</button>
                  <button className="button primary" type="button" onClick={() => openDecision("reject", selected.map((item) => item.id), true)}>Rejeitar</button>
                </>
              ) : (
                <button className="button primary" type="button" onClick={() => openDecision("reopen", selected.map((item) => item.id), true)}>Reabrir</button>
              )}
            </div>
          )}

          <div className="opportunity-sort-controls">
            <label>
              <span>Ordenar por</span>
             