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
import { api, formatDate } from "@/lib/api";
import { formatAccountLabel, formatMoney, providerLabel } from "@/lib/cloud.mjs";
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
    : `${formatMoney(finding.estimated_monthly_savings, finding.currency)}/mês`;
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
    state.accountId, state.collectionRunId, state.current, state.order, state.page, state.pageSize,
    state.provider, state.region, state.resourceId, state.resourceType, state.rule, state.search,
    state.service, state.severity, state.sort, state.status,
  ]);
  const statsQuery = useMemo(() => buildOpportunityStatsQuery(state), [
    state.accountId, state.collectionRunId, state.current, state.provider, state.region,
    state.resourceId, state.resourceType, state.rule, state.search, state.service, state.severity,
  ]);

  const optionsQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "300" });
    if (state.provider) params.set("provider", state.provider);
    if (state.accountId) params.set("account_id", state.accountId);
    return params.toString();
  }, [state.accountId, state.provider]);

  const listPlaceholderIdentity = useMemo(
    () =>
      JSON.stringify({
        status: state.status,
        provider: state.provider,
        accountId: state.accountId,
        region: state.region,
        service: state.service,
        resourceType: state.resourceType,
        severity: state.severity,
        rule: state.rule,
        collectionRunId: state.collectionRunId,
        resourceId: state.resourceId,
        search: state.search,
        current: state.current,
        pageSize: state.pageSize,
        sort: state.sort,
        order: state.order,
      }),
    [
      state.accountId,
      state.collectionRunId,
      state.current,
      state.order,
      state.pageSize,
      state.provider,
      state.region,
      state.resourceId,
      state.resourceType,
      state.rule,
      state.search,
      state.service,
      state.severity,
      state.sort,
      state.status,
    ],
  );

  const optionsRequest = useApiQuery<OpportunityOptions>({
    key: queryKeys.opportunities.options(state.provider, state.accountId),
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

  const findings = listRequest.data?.items ?? [];
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
    setSelectedIds(new Set());
  }, [listQuery]);

  useEffect(() => {
    const pageData = listRequest.data;
    if (!pageData || state.page >= pageData.total_pages) return;
    const nextQuery = buildOpportunityApiQuery({
      ...state,
      page: state.page + 1,
    });
    void prefetchApiQuery<OpportunityPage>({
      key: queryKeys.opportunities.list(nextQuery),
      path: `/opportunities?${nextQuery}`,
      ...cachePolicy.operational,
    }).catch(() => undefined);
  }, [listRequest.data, state]);

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
  const pageSavings = findings.reduce<Record<string, number>>((totals, finding) => {
    const currency = finding.currency || "USD";
    totals[currency] = (totals[currency] || 0) + Number(finding.estimated_monthly_savings);
    return totals;
  }, {});
  const newestObservation = findings.reduce<string | null>((latest, finding) => {
    if (!latest || new Date(finding.last_seen_at) > new Date(latest)) return finding.last_seen_at;
    return latest;
  }, null);
  const currentAccount = options.accounts.find(
    (account) => account.provider === state.provider && account.account_id === state.accountId,
  );
  const accountOptions = options.accounts.filter(
    (account) => !state.provider || account.provider === state.provider,
  );
  const providerOptions = Array.from(new Set([
    ...options.providers.map((provider) => provider.toLowerCase()),
    ...collectionRuns.map((run) => run.provider.toLowerCase()),
    ...(state.provider ? [state.provider.toLowerCase()] : []),
  ])).sort();
  const visibleCollectionRuns = collectionRuns.filter((run) =>
    (!state.provider || run.provider.toLowerCase() === state.provider.toLowerCase()) &&
    (!state.accountId || run.account_id === state.accountId),
  );
  const pages = pageWindow(state.page, totalPages);
  const hasFilters = Boolean(
    state.provider || state.accountId || state.region || state.service || state.resourceType ||
    state.severity || state.rule ||
    state.collectionRunId || state.resourceId || state.search || state.current,
  );
  const activeFilters = [
    state.provider ? `Cloud: ${providerLabel(state.provider)}` : "",
    state.accountId ? `Conta: ${formatAccountLabel(currentAccount?.account_name, state.accountId)}` : "",
    state.severity ? `Severidade: ${state.severity === "high" ? "Alta" : state.severity === "medium" ? "Média" : "Baixa"}` : "",
    state.region ? `Região: ${state.region}` : "",
    state.service ? `Serviço: ${state.service}` : "",
    state.resourceType ? `Tipo: ${state.resourceType}` : "",
    state.rule ? `Regra: ${state.rule}` : "",
    state.search ? `Busca: ${state.search}` : "",
    state.collectionRunId ? `Coleta: ${state.collectionRunId.slice(0, 8)}` : "",
    state.current ? "Escopo: estado atual" : "",
  ].filter(Boolean);

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
      service: null,
      resource_type: null,
      severity: null,
      rule: null,
      rule_key: null,
      collection_run_id: null,
      resource_id: null,
      search: null,
      current: null,
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
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.dashboard.all);
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
    const match = accountOptions.find((account) => account.account_id === value);
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
          <div><ListFilter size={18} /><strong>Filtros</strong><span>Combinados no servidor e persistidos na URL{state.current ? " · Estado atual das últimas coletas válidas" : ""}</span></div>
          {hasFilters && <button className="filter-clear" type="button" onClick={clearFilters}><X size={15} /> Limpar filtros</button>}
        </div>
        {activeFilters.length > 0 && (
          <div className="active-filter-summary" aria-label="Filtros ativos">
            {activeFilters.map((label) => <span key={label}>{label}</span>)}
          </div>
        )}
        <div className="opportunity-filter-grid">
          <label className="opportunity-filter search-filter">
            <span>Busca</span>
            <div><Search size={16} /><input value={searchInput} placeholder="Recurso, título, regra ou serviço" onChange={(event) => setSearchInput(event.target.value)} /></div>
          </label>

          <label className="opportunity-filter">
            <span>Cloud</span>
            <div><Cloud size={16} /><select value={state.provider} onChange={(event) => updateUrl({ provider: event.target.value, account_id: null, collection_run_id: null })}>
              <option value="">Todas as clouds</option>
              {providerOptions.map((provider) => <option key={provider} value={provider}>{providerLabel(provider)}</option>)}
            </select></div>
          </label>

          <label className="opportunity-filter account-filter">
            <span>Conta</span>
            <div><Building2 size={16} /><input
              list="opportunity-account-options"
              value={accountInput}
              placeholder={filtersLoading ? "Carregando contas…" : "Buscar por nome ou ID da conta"}
              onChange={(event) => {
                const value = event.target.value;
                setAccountInput(value);
                if (!value) updateUrl({ account_id: null, collection_run_id: null });
                else if (accountOptions.some((account) => account.account_id === value)) {
                  updateUrl({ account_id: value, collection_run_id: null });
                }
              }}
              onBlur={commitAccountInput}
              onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
            /></div>
            {currentAccount && (
              <small>
                {currentAccount.account_name || currentAccount.account_id} · {providerLabel(currentAccount.provider)}
              </small>
            )}
            <datalist id="opportunity-account-options">
              {accountOptions.map((account) => (
                <option key={`${account.provider}:${account.account_id}`} value={account.account_id}>
                  {account.account_name || account.account_id} · {providerLabel(account.provider)}
                </option>
              ))}
            </datalist>
          </label>

          <label className="opportunity-filter">
            <span>Região</span>
            <div><Filter size={16} /><input
              list="opportunity-region-options"
              value={regionInput}
              placeholder="Qualquer região ou escopo regional"
              onChange={(event) => setRegionInput(event.target.value)}
              onBlur={() => { if (regionInput.trim() !== state.region) updateUrl({ region: regionInput.trim() }); }}
              onKeyDown={(event) => { if (event.key === "Enter") event.currentTarget.blur(); }}
            /></div>
            <datalist id="opportunity-region-options">
              {options.regions.map((region) => <option key={region} value={region} />)}
            </datalist>
          </label>

          <label className="opportunity-filter">
            <span>Serviço</span>
            <div><Filter size={16} /><select value={state.service} onChange={(event) => updateUrl({ service: event.target.value })}>
              <option value="">Todos os serviços</option>
              {options.services.map((service) => <option key={service} value={service}>{service}</option>)}
            </select></div>
          </label>

          <label className="opportunity-filter">
            <span>Tipo de recurso</span>
            <div><Filter size={16} /><select value={state.resourceType} onChange={(event) => updateUrl({ resource_type: event.target.value })}>
              <option value="">Todos os tipos</option>
              {options.resource_types.map((resourceType) => <option key={resourceType} value={resourceType}>{resourceType}</option>)}
            </select></div>
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
              {options.rules.map((rule) => <option key={rule} value={rule}>{rule}</option>)}
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
                  {formatDate(run.started_at)} · {providerLabel(run.provider)} · {run.account_id} · {run.status}
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
          <strong>
            {Object.entries(pageSavings).length
              ? Object.entries(pageSavings)
                  .map(([currency, amount]) => formatMoney(amount, currency))
                  .join(" · ")
              : "—"}
          </strong>
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
              <select value={state.sort} onChange={(event) => updateUrl({ sort: event.target.value })}>
                {sortOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Ordem</span>
              <select value={state.order} onChange={(event) => updateUrl({ order: event.target.value })}>
                <option value="desc">Decrescente</option>
                <option value="asc">Crescente</option>
              </select>
            </label>
          </div>
        </div>

        {loading && findings.length > 0 && <div className="table-loading-bar" role="status"><span /> Atualizando resultados…</div>}
        {listError && (
          <div className="opportunity-inline-error" role="alert">
            <div><strong>Não foi possível carregar as oportunidades.</strong><span>{listError}</span></div>
            <button className="button ghost" type="button" onClick={() => void listRequest.refetch()}>Tentar novamente</button>
          </div>
        )}

        <div className="data-table-wrap opportunity-table-wrap" role="region" aria-label="Backlog de oportunidades" tabIndex={0}>
          <table className="data-table opportunities-table stage-five-table">
            <thead>
              <tr>
                <th scope="col" className="selection-cell">Seleção</th>
                <th scope="col">Oportunidade</th>
                <th scope="col">Contexto</th>
                <th scope="col">Risco</th>
                <th scope="col">Impacto</th>
                <th scope="col">Detecções</th>
                <th scope="col">Ações</th>
              </tr>
            </thead>
            {loading && !findings.length ? <SkeletonRows /> : (
              <tbody>
                {findings.map((finding) => (
                  <tr
                    key={finding.id}
                    className={selectedIds.has(finding.id) ? "selected-row" : undefined}
                    onMouseEnter={() => {
                      void prefetchApiQuery({
                        key: queryKeys.opportunities.detail(finding.id),
                        path: `/opportunities/${finding.id}`,
                        ...cachePolicy.detail,
                      }).catch(() => undefined);
                    }}
                  >
                    <td className="selection-cell">
                      <label className="selection-control compact-check">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(finding.id)}
                          aria-label={`Selecionar ${finding.title} · ${finding.resource_id}`}
                          onChange={() => toggleSelection(finding.id)}
                        />
                      </label>
                    </td>
                    <td className="opportunity-primary-cell">
                      <button className="opportunity-title-button" type="button" onClick={() => openDetail(finding.id)}>{finding.title}</button>
                      <span className="opportunity-rule">{finding.rule_key}</span>
                      <strong className="opportunity-resource">{finding.resource_name || finding.resource_id}</strong>
                      {finding.resource_name && <span>{finding.resource_id}</span>}
                    </td>
                    <td className="opportunity-context-cell">
                      <strong>{providerLabel(finding.provider)} · {finding.account_name || finding.account_id}</strong>
                      <span>{finding.account_id}</span>
                      <span>{finding.region || "Sem região"} · {finding.service || "Sem serviço"}</span>
                      {finding.resource_type && <span>{finding.resource_type}</span>}
                    </td>
                    <td>
                      <div className="risk-badges"><StatusBadge value={finding.severity} /><StatusBadge value={finding.status} /></div>
                      {finding.needs_review && <span className="review-inline">Detectada novamente</span>}
                    </td>
                    <td className="money-cell opportunity-impact-cell">
                      {savingsLabel(finding)}
                      <span>Custo atual: {formatMoney(finding.current_monthly_cost, finding.currency)}</span>
                    </td>
                    <td className="detection-cell">
                      <span><strong>Primeira</strong>{formatDate(finding.first_seen_at)}</span>
                      <span><strong>Última</strong>{formatDate(finding.last_seen_at)}</span>
                    </td>
                    <td>
                      <div className="row-actions stage-five-actions">
                        <button type="button" onClick={() => openDetail(finding.id)}>Abrir detalhe</button>
                        {finding.status === "open" ? (
                          <>
                            <button type="button" onClick={() => openDecision("treat", [finding.id], false)}>Tratar</button>
                            <button type="button" onClick={() => openDecision("reject", [finding.id], false)}>Rejeitar</button>
                          </>
                        ) : (
                          <button type="button" onClick={() => openDecision("reopen", [finding.id], false)}>Reabrir</button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            )}
          </table>

          {!loading && !listError && !findings.length && (
            <div className="opportunity-empty-state">
              <Filter size={24} />
              <strong>Nenhuma oportunidade {state.status === "open" ? "aberta" : state.status === "treated" ? "tratada" : "rejeitada"} encontrada.</strong>
              <p>{hasFilters ? "Os filtros selecionados não retornaram resultados." : "Ainda não existem oportunidades nesse estado para as coletas disponíveis."}</p>
              {hasFilters && <button className="button ghost" type="button" onClick={clearFilters}>Limpar filtros</button>}
            </div>
          )}
        </div>

        <footer className="opportunity-pagination">
          <div>
            <span>Página {totalPages ? state.page : 0} de {totalPages} · {total} resultado(s)</span>
            <label>
              Itens por página
              <select value={state.pageSize} onChange={(event) => updateUrl({ page_size: event.target.value })}>
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </label>
          </div>
          <nav className="page-buttons" aria-label="Paginação das oportunidades">
            <button type="button" aria-label="Página anterior" disabled={loading || state.page <= 1} onClick={() => updateUrl({ page: state.page - 1 }, { resetPage: false })}><ChevronLeft size={18} /></button>
            {pages.map((page) => (
              <button
                type="button"
                key={page}
                aria-current={page === state.page ? "page" : undefined}
                className={page === state.page ? "active" : undefined}
                disabled={loading}
                onClick={() => updateUrl({ page }, { resetPage: false })}
              >{page}</button>
            ))}
            <button type="button" aria-label="Próxima página" disabled={loading || state.page >= totalPages} onClick={() => updateUrl({ page: state.page + 1 }, { resetPage: false })}><ChevronRight size={18} /></button>
          </nav>
        </footer>
      </section>

      {state.opportunityId && (
        <OpportunityDetail
          opportunityId={state.opportunityId}
          onClose={closeDetail}
          onAction={(action, id) => openDecision(action, [id], false)}
        />
      )}

      {decision && (
        <OpportunityDecisionDialog
          action={decision.action}
          count={decision.ids.length}
          saving={decisionSaving}
          error={decisionError}
          onClose={() => { if (!decisionSaving) { setDecision(null); setDecisionError(""); } }}
          onSubmit={submitDecision}
        />
      )}
    </>
  );
}
