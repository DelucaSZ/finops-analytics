"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { RefreshCw } from "lucide-react";
import { CollectionComparisonActions } from "@/components/collection-comparison-actions";
import {
  AccountSelector,
  FilterBar,
  PageHeader,
  ProviderBadge,
  ProviderSelector,
  Section,
  StatusIndicator,
} from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  EmptyState,
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
} from "@/components/ui";
import { ApiError, formatDate } from "@/lib/api";
import { formatAccountLabel, formatNumber, providerLabel } from "@/lib/cloud.mjs";
import {
  COLLECTION_STATUSES,
  buildCollectionQuery,
  collectionOpportunitiesUrl,
  durationLabel,
  localDateTime,
  parseCollectionQuery,
  patchCollectionQuery,
} from "@/lib/collection-query.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { prefetchApiQuery, useApiQuery } from "@/lib/server-state";
import type {
  CollectionDetail,
  CollectionItem,
  CollectionOptions,
  CollectionPage,
} from "@/lib/types";
import styles from "./collection-workspace.module.css";

const number = (value: number) => formatNumber(value);

function preciseDate(value: string | null) {
  return value ? new Date(value).toLocaleString("pt-BR") : "—";
}

function runStatusTone(run: CollectionItem) {
  if (run.status === "SUCCESS") return run.has_warnings ? "warning" as const : "success" as const;
  if (run.status === "FAILED") return "danger" as const;
  if (run.status === "RUNNING") return "pending" as const;
  return "neutral" as const;
}

function RunStatus({ run }: { run: CollectionItem }) {
  const label = COLLECTION_STATUSES[run.status] || run.status;
  return (
    <StatusIndicator
      status={runStatusTone(run)}
      label={run.has_warnings && run.status === "SUCCESS" ? `${label} · com avisos` : label}
    />
  );
}

function RunLink({
  run,
  href,
}: {
  run: CollectionItem | null;
  href: (id: string) => string;
}) {
  return run ? (
    <span className={styles.statusCell}>
      <Link className={styles.reportLink} href={href(run.id)}>
        {formatDate(run.started_at)}
      </Link>
      <RunStatus run={run} />
    </span>
  ) : (
    <span className={styles.secondary}>Nenhuma registrada</span>
  );
}

function CollectionTableState({
  loading,
  error,
  empty,
  hasFilters,
  page,
  onRetry,
  onClear,
}: {
  loading: boolean;
  error: string;
  empty: boolean;
  hasFilters: boolean;
  page: number;
  onRetry: () => void;
  onClear: () => void;
}) {
  if (loading) {
    return (
      <TableBody>
        {Array.from({ length: 5 }, (_, row) => (
          <TableRow key={row} staticRow>
            {Array.from({ length: 6 }, (_, cell) => (
              <TableCell key={cell}><Skeleton /></TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    );
  }

  if (error) {
    return (
      <TableBody>
        <TableRow staticRow>
          <TableCell colSpan={6}>
            <Alert
              variant="danger"
              title="Não foi possível carregar os relatórios"
              description={error}
              actions={<Button type="button" variant="outline" size="sm" onClick={onRetry}>Tentar novamente</Button>}
            />
          </TableCell>
        </TableRow>
      </TableBody>
    );
  }

  if (empty) {
    const title = hasFilters
      ? "Nenhum relatório corresponde aos filtros atuais"
      : page > 1
        ? "Nenhum relatório nesta página"
        : "Nenhum relatório foi processado ainda";
    const description = hasFilters
      ? "Ajuste o escopo, o status, o período ou a versão dos analyzers."
      : page > 1
        ? "Volte para uma página anterior para consultar o histórico disponível."
        : "As execuções concluídas e em andamento aparecerão aqui.";
    return (
      <TableBody>
        <TableRow staticRow>
          <TableCell colSpan={6}>
            <EmptyState
              title={title}
              description={description}
              primaryAction={hasFilters ? <Button type="button" variant="outline" size="sm" onClick={onClear}>Limpar filtros</Button> : undefined}
            />
          </TableCell>
        </TableRow>
      </TableBody>
    );
  }

  return null;
}

export function CollectionWorkspace({
  collectionId,
  headerAction,
}: {
  collectionId?: string;
  headerAction?: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const state = useMemo(() => parseCollectionQuery(search), [search]);
  const query = buildCollectionQuery(state);
  const [draft, setDraft] = useState(state);
  const [validation, setValidation] = useState("");
  const [now, setNow] = useState(Date.now());
  const [accountSearch, setAccountSearch] = useState(state.account_id);
  const [optionScope, setOptionScope] = useState({
    provider: state.provider,
    search: state.account_id,
  });

  const listPlaceholderIdentity = useMemo(
    () => buildCollectionQuery({ ...state, page: 1 }),
    [state],
  );
  const optionQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "50" });
    if (optionScope.provider) params.set("provider", optionScope.provider);
    if (optionScope.search) params.set("search", optionScope.search);
    return params.toString();
  }, [optionScope.provider, optionScope.search]);

  const listRequest = useApiQuery<CollectionPage>({
    key: queryKeys.collections.list(query),
    path: `/collections?${query}`,
    enabled: !collectionId,
    ...cachePolicy.operational,
    keepPreviousData: true,
    placeholderIdentity: listPlaceholderIdentity,
  });
  const detailRequest = useApiQuery<CollectionDetail>({
    key: queryKeys.collections.detail(collectionId || ""),
    path: `/collections/${encodeURIComponent(collectionId || "")}`,
    enabled: Boolean(collectionId),
    ...cachePolicy.detail,
  });
  const optionsRequest = useApiQuery<CollectionOptions>({
    key: queryKeys.collections.options(optionScope.provider, optionScope.search, 50),
    path: `/collections/options?${optionQuery}`,
    enabled: !collectionId,
    ...cachePolicy.metadata,
  });

  const data = listRequest.data ?? null;
  const detail = detailRequest.data ?? null;
  const options = optionsRequest.data ?? {
    providers: [],
    accounts: [],
    has_more_accounts: false,
  };
  const loading = collectionId ? detailRequest.isLoading : listRequest.isLoading;
  const refreshing = collectionId
    ? detailRequest.isFetching && !detailRequest.isLoading
    : listRequest.isFetching && !listRequest.isLoading;
  const requestError = collectionId ? detailRequest.error : listRequest.error;
  const error = requestError
    ? requestError instanceof ApiError && requestError.status === 404
      ? "Relatório não encontrado."
      : collectionId
        ? "Não foi possível carregar este relatório."
        : "Não foi possível carregar o histórico de relatórios."
    : "";

  const hasFilters = Boolean(
    state.provider ||
    state.account_id ||
    state.status ||
    state.date_from ||
    state.date_to ||
    state.analyzer_version,
  );
  const selectedAccount = options.accounts.find(
    (account) => account.account_id === state.account_id && (!state.provider || account.provider === state.provider),
  );
  const activeFilters = [
    state.provider ? `Cloud: ${providerLabel(state.provider)}` : "",
    state.account_id ? `Conta: ${formatAccountLabel(selectedAccount?.account_name, state.account_id)}` : "",
    state.status ? `Status: ${COLLECTION_STATUSES[state.status] || state.status}` : "",
    state.analyzer_version ? `Versão: ${state.analyzer_version}` : "",
    state.date_from ? `A partir de: ${preciseDate(state.date_from)}` : "",
    state.date_to ? `Até: ${preciseDate(state.date_to)}` : "",
  ].filter(Boolean);
  const detailHref = (id: string) => `/collections/${encodeURIComponent(id)}?${query}`;
  const change = (patch: Record<string, string | number>) =>
    router.push(`${pathname}?${patchCollectionQuery(search, patch)}`, { scroll: false });
  const clearFilters = () => router.push("/collections", { scroll: false });

  useEffect(() => {
    setDraft(state);
    setAccountSearch(state.account_id);
    setValidation("");
  }, [state]);

  useEffect(() => {
    if (collectionId) return;
    const timer = window.setTimeout(() => {
      setOptionScope({ provider: draft.provider, search: accountSearch });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [accountSearch, collectionId, draft.provider]);

  const hasRunning = collectionId
    ? detail?.status === "RUNNING"
    : Boolean(data?.items.some((run) => run.status === "RUNNING"));

  useEffect(() => {
    if (!hasRunning) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      setNow(Date.now());
      if (collectionId) void detailRequest.refetch();
      else void listRequest.refetch();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [collectionId, detailRequest.refetch, hasRunning, listRequest.refetch]);

  const refresh = () => {
    if (collectionId) void detailRequest.refetch();
    else {
      void listRequest.refetch();
      void optionsRequest.refetch();
    }
  };

  const headerActions = (
    <div className={styles.headerActions}>
      {collectionId ? (
        <Button type="button" variant="outline" onClick={() => router.push(`/collections?${query}`)}>
          Voltar ao histórico
        </Button>
      ) : headerAction}
      <Button
        type="button"
        variant="outline"
        leadingIcon={<RefreshCw {...iconDefaults} />}
        loading={refreshing}
        disabled={loading}
        onClick={refresh}
      >
        Atualizar
      </Button>
    </div>
  );

  const providerOptions = options.providers.map((provider) => ({
    value: provider,
    label: providerLabel(provider),
  }));
  const accountOptions = options.accounts
    .filter((account) => !draft.provider || account.provider === draft.provider)
    .map((account) => ({
      value: account.account_id,
      label: account.account_name || account.account_id,
      accountId: account.account_id,
      provider: providerLabel(account.provider),
      searchTerms: [account.account_id, account.provider],
    }));
  const statusOptions = [
    { value: "", label: "Todos os status" },
    ...Object.entries(COLLECTION_STATUSES).map(([value, label]) => ({ value, label })),
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title={collectionId ? `Relatório #${collectionId.slice(0, 8)}` : "Relatórios"}
        description={collectionId
          ? "Consulte o escopo, o processamento e os resultados persistidos desta execução."
          : "Acompanhe execuções por cloud e conta, consulte o histórico e entenda o status de processamento."}
        metadata={<span className={styles.pollingNote}>Atualização automática a cada 15 s somente durante execuções em andamento e com a aba visível.</span>}
        actions={headerActions}
      />

      {!collectionId ? (
        <form
          className={styles.filterForm}
          onSubmit={(event) => {
            event.preventDefault();
            if (draft.date_from && draft.date_to && new Date(draft.date_from) >= new Date(draft.date_to)) {
              setValidation("O início deve ser anterior ao fim do período.");
              return;
            }
            setValidation("");
            change({ ...draft, page: 1 });
          }}
        >
          <FilterBar
            aria-label="Filtros de relatórios"
            clearAction={hasFilters ? <Button type="button" variant="ghost" size="sm" onClick={clearFilters}>Limpar filtros</Button> : undefined}
            actions={(
              <div className={styles.toolbar}>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const end = new Date();
                    const start = new Date(end);
                    start.setDate(start.getDate() - 30);
                    change({
                      ...draft,
                      date_from: start.toISOString(),
                      date_to: end.toISOString(),
                      page: 1,
                    });
                  }}
                >
                  Últimos 30 dias
                </Button>
                <Button type="submit" size="sm">Aplicar filtros</Button>
              </div>
            )}
          >
            <div className={styles.filterControls}>
              {optionsRequest.error ? (
                <>
                  <Input
                    label="Cloud"
                    placeholder="Cloud exata"
                    value={draft.provider}
                    onChange={(event) => setDraft({ ...draft, provider: event.target.value, account_id: "" })}
                  />
                  <Input
                    label="Conta"
                    placeholder="ID exato da conta"
                    value={draft.account_id}
                    onChange={(event) => setDraft({ ...draft, account_id: event.target.value })}
                  />
                </>
              ) : (
                <>
                  <ProviderSelector
                    label="Cloud"
                    value={draft.provider}
                    onChange={(provider) => {
                      setDraft({ ...draft, provider, account_id: "" });
                      setAccountSearch("");
                    }}
                    options={providerOptions}
                    loading={optionsRequest.isLoading}
                    placeholder="Todas as clouds"
                    clearLabel="Todas as clouds"
                    searchable={false}
                  />
                  <AccountSelector
                    label="Conta"
                    value={draft.account_id}
                    onChange={(account_id) => {
                      setDraft({ ...draft, account_id });
                      if (!account_id) setAccountSearch("");
                    }}
                    onSearchChange={setAccountSearch}
                    searchPlaceholder="Buscar conta por nome ou ID"
                    options={accountOptions}
                    loading={optionsRequest.isLoading}
                    placeholder="Todas as contas"
                    clearLabel="Todas as contas"
                  />
                </>
              )}
              <Select
                label="Status"
                value={draft.status}
                options={statusOptions}
                onChange={(event) => setDraft({ ...draft, status: event.target.value })}
              />
              <Input
                type="datetime-local"
                label="Início do período"
                helperText="Inclusivo, no fuso local do navegador."
                value={localDateTime(draft.date_from)}
                onChange={(event) => setDraft({
                  ...draft,
                  date_from: event.target.value ? new Date(event.target.value).toISOString() : "",
                })}
              />
              <Input
                type="datetime-local"
                label="Fim do período"
                helperText="Exclusivo, no fuso local do navegador."
                value={localDateTime(draft.date_to)}
                onChange={(event) => setDraft({
                  ...draft,
                  date_to: event.target.value ? new Date(event.target.value).toISOString() : "",
                })}
              />
              <Input
                label="Versão dos analyzers"
                placeholder="Todas as versões"
                value={draft.analyzer_version}
                onChange={(event) => setDraft({ ...draft, analyzer_version: event.target.value })}
              />
            </div>
          </FilterBar>

          {activeFilters.length > 0 ? (
            <div className={styles.activeFilters} aria-label="Filtros ativos">
              {activeFilters.map((label) => <Badge key={label}>{label}</Badge>)}
            </div>
          ) : null}
          {options.has_more_accounts ? <p className={styles.note}>Busque pelo nome ou identificador da conta para consultar além das primeiras opções carregadas.</p> : null}
          {optionsRequest.error ? (
            <Alert
              variant="warning"
              title="Sugestões de filtro indisponíveis"
              description="Informe a cloud e o identificador da conta manualmente; o histórico continua consultável."
            />
          ) : null}
          {validation ? <Alert variant="danger" title="Período inválido" description={validation} /> : null}
        </form>
      ) : null}

      {!collectionId && data?.account_summary ? (
        <Section
          appearance="card"
          title="Contexto da conta"
          description="Últimas execuções considerando todo o histórico da conta e cloud selecionadas."
        >
          <dl className={styles.summaryGrid}>
            <div className={styles.summaryItem}>
              <dt>Última execução</dt>
              <dd><RunLink run={data.account_summary.latest_run} href={detailHref} /></dd>
            </div>
            <div className={styles.summaryItem}>
              <dt>Última conclusão com sucesso</dt>
              <dd><RunLink run={data.account_summary.latest_success} href={detailHref} /></dd>
            </div>
          </dl>
          <p className={styles.note}>Uma conclusão com avisos pode conter resultados incompletos.</p>
        </Section>
      ) : null}

      {!collectionId ? (
        <Section
          title="Histórico de relatórios"
          description="Execuções persistidas por cloud e conta. O histórico mais recente aparece primeiro por padrão."
          actions={(
            <div className={styles.sectionActions}>
              {refreshing ? <StatusIndicator status="pending" label="Atualizando" /> : null}
              <Select
                label="Ordenar por"
                controlSize="sm"
                value={state.sort}
                onChange={(event) => change({ sort: event.target.value })}
                options={[
                  { value: "started_at", label: "Início" },
                  { value: "opportunities_found", label: "Oportunidades encontradas" },
                ]}
              />
              <Select
                label="Direção"
                controlSize="sm"
                value={state.order}
                onChange={(event) => change({ order: event.target.value })}
                options={[
                  { value: "desc", label: "Decrescente" },
                  { value: "asc", label: "Crescente" },
                ]}
              />
            </div>
          )}
        >
          <div className={styles.tableMeta}>
            <span>{data ? `${number(data.total)} relatório(s)` : "Contagem indisponível"}</span>
            <span>Período aplicado ao início da execução.</span>
          </div>
          <Table aria-label="Histórico de relatórios" aria-busy={loading || refreshing}>
            <TableHeader>
              <TableRow staticRow>
                <TableHead>Relatório</TableHead>
                <TableHead>Escopo</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duração</TableHead>
                <TableHead numeric>Recursos</TableHead>
                <TableHead numeric>Oportunidades</TableHead>
              </TableRow>
            </TableHeader>
            {loading || error || !data?.items.length ? (
              <CollectionTableState
                loading={loading}
                error={error}
                empty={!loading && !error && data !== null && data.items.length === 0}
                hasFilters={hasFilters}
                page={state.page}
                onRetry={() => void listRequest.refetch()}
                onClear={clearFilters}
              />
            ) : (
              <TableBody>
                {data.items.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      <div className={styles.reportCell}>
                        <Link
                          className={styles.reportLink}
                          href={detailHref(run.id)}
                          onMouseEnter={() => {
                            void prefetchApiQuery({
                              key: queryKeys.collections.detail(run.id),
                              path: `/collections/${encodeURIComponent(run.id)}`,
                              ...cachePolicy.detail,
                            }).catch(() => undefined);
                          }}
                        >
                          {formatDate(run.started_at)}
                        </Link>
                        <span className={styles.secondary}>Fim: {formatDate(run.finished_at)}</span>
                        <span className={styles.technicalId}>{run.id.slice(0, 8)}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className={styles.scopeCell}>
                        <div className={styles.scopePrimary}>
                          <ProviderBadge provider={run.provider} />
                          <strong>{run.account_name || run.account_id}</strong>
                        </div>
                        {run.account_name ? <span className={styles.secondary}>{run.account_id}</span> : null}
                      </div>
                    </TableCell>
                    <TableCell><RunStatus run={run} /></TableCell>
                    <TableCell>{durationLabel(run, now)}</TableCell>
                    <TableCell numeric>
                      {run.resources_analyzed_available ? number(run.resources_analyzed) : "Não disponível"}
                    </TableCell>
                    <TableCell numeric>
                      {run.status === "RUNNING" ? "Aguardando conclusão" : number(run.opportunities_found)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            )}
          </Table>

          {data ? (
            <div className={styles.paginationRow}>
              <Select
                label="Linhas por página"
                controlSize="sm"
                value={String(state.page_size)}
                onChange={(event) => change({ page_size: Number(event.target.value), page: 1 })}
                options={[25, 50, 100].map((size) => ({ value: String(size), label: String(size) }))}
              />
              {data.total_pages > 1 ? (
                <Pagination page={state.page} pageCount={data.total_pages} onPageChange={(page) => change({ page })} />
              ) : null}
            </div>
          ) : null}
          <p className={styles.note}>Recursos analisados podem estar indisponíveis em execuções históricas. O total de oportunidades é persistido quando a execução termina.</p>
        </Section>
      ) : null}

      {collectionId && error ? (
        <Alert
          variant="danger"
          title="Não foi possível carregar o relatório"
          description={error}
          actions={<Button type="button" variant="outline" size="sm" onClick={() => void detailRequest.refetch()}>Tentar novamente</Button>}
        />
      ) : null}

      {collectionId && loading ? (
        <Section title="Carregando relatório"><Skeleton /><Skeleton /><Skeleton /></Section>
      ) : null}

      {collectionId && detail ? (
        <Section
          appearance="card"
          title="Detalhes da execução"
          description="Estado funcional e metadados persistidos da CollectionRun."
          actions={<RunStatus run={detail} />}
        >
          <div className={styles.detailStack}>
            <div className={styles.detailHeader}>
              <div className={styles.detailTitleGroup}>
                <h3 className={styles.detailTitle}>CollectionRun</h3>
                <span className={styles.technicalId}>{detail.id}</span>
              </div>
              <div className={styles.detailActions}>
                {detail.detailed_observations_available ? (
                  <Button type="button" onClick={() => router.push(collectionOpportunitiesUrl(detail.id))}>
                    Ver oportunidades desta coleta
                  </Button>
                ) : null}
              </div>
            </div>

            {!detail.detailed_observations_available ? (
              <Alert
                variant="warning"
                title="Detalhes históricos expirados"
                description="O resumo desta CollectionRun foi preservado, mas as observações detalhadas não estão mais disponíveis pela política de retenção."
              />
            ) : null}
            {detail.status === "FAILED" ? (
              <Alert
                variant="danger"
                title="Falha durante o processamento"
                description={detail.error_detail || "O motivo da falha não foi registrado."}
              />
            ) : null}
            {detail.has_warnings ? (
              <Alert
                variant="warning"
                title="Concluída com avisos"
                description={detail.warning_detail || "Um ou mais analyzers não concluíram a coleta; os resultados podem estar incompletos."}
              />
            ) : null}
            {detail.status === "RUNNING" ? (
              <Alert
                variant="info"
                title="Processamento em andamento"
                description={`${durationLabel(detail, now)}. As métricas finais ainda não estão disponíveis.`}
              />
            ) : null}

            {detail.detailed_observations_available ? <CollectionComparisonActions run={detail} /> : null}

            <dl className={styles.metadataGrid}>
              <div className={styles.metadataItem}>
                <dt>Cloud</dt>
                <dd><ProviderBadge provider={detail.provider} /></dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Conta</dt>
                <dd>{detail.account_name || detail.account_id}{detail.account_name ? <span className={styles.secondary}>{detail.account_id}</span> : null}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Início</dt>
                <dd>{preciseDate(detail.started_at)}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Fim</dt>
                <dd>{preciseDate(detail.finished_at)}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Duração</dt>
                <dd>{durationLabel(detail, now)}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Versão dos analyzers</dt>
                <dd>{detail.analyzer_version || "Não registrada"}</dd>
              </div>
              {detail.trigger ? (
                <div className={styles.metadataItem}>
                  <dt>Gatilho</dt>
                  <dd>{detail.trigger === "manual" ? "Manual" : detail.trigger === "scheduled" ? "Agendada" : detail.trigger}</dd>
                </div>
              ) : null}
              {detail.scan_id ? (
                <div className={styles.metadataItem}>
                  <dt>Scan de origem</dt>
                  <dd><span className={styles.technicalId}>{detail.scan_id}</span></dd>
                </div>
              ) : null}
              <div className={styles.metadataItem}>
                <dt>Recursos analisados</dt>
                <dd>{detail.resources_analyzed_available ? number(detail.resources_analyzed) : "Não disponível"}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Oportunidades encontradas</dt>
                <dd>{detail.status === "RUNNING" ? "Aguardando conclusão" : number(detail.opportunities_found)}</dd>
              </div>
              <div className={styles.metadataItem}>
                <dt>Detalhes de observação retidos</dt>
                <dd>{number(detail.opportunities_observed)}</dd>
              </div>
            </dl>

            <p className={styles.note}>O total encontrado é persistido na CollectionRun. A contagem de detalhes retidos representa somente observations ainda disponíveis no banco.</p>
          </div>
        </Section>
      ) : null}
    </div>
  );
}
