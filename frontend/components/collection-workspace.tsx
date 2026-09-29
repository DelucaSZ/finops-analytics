"use client";

import Link from "next/link";
import { CollectionComparisonActions } from "@/components/collection-comparison-actions";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, Clock3, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ApiError, formatDate } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { prefetchApiQuery, useApiQuery } from "@/lib/server-state";
import {
  COLLECTION_STATUSES,
  buildCollectionQuery,
  collectionOpportunitiesUrl,
  durationLabel,
  localDateTime,
  parseCollectionQuery,
  patchCollectionQuery,
} from "@/lib/collection-query.mjs";
import type {
  CollectionDetail,
  CollectionItem,
  CollectionOptions,
  CollectionPage,
} from "@/lib/types";

const number = (value: number) => value.toLocaleString("pt-BR");
function preciseDate(value: string | null) {
  return value ? new Date(value).toLocaleString("pt-BR") : "—";
}

function RunStatus({ run }: { run: CollectionItem }) {
  const Icon =
    run.status === "SUCCESS"
      ? CheckCircle2
      : run.status === "FAILED"
        ? CircleAlert
        : Clock3;
  return (
    <span
      className={`collection-status collection-${run.status.toLowerCase()}`}
    >
      <Icon size={16} aria-hidden="true" />
      {COLLECTION_STATUSES[run.status] || run.status}
      {run.has_warnings ? " · com avisos" : ""}
    </span>
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
    <Link href={href(run.id)}>
      <RunStatus run={run} /> · {formatDate(run.started_at)}
    </Link>
  ) : (
    <span>Nenhuma registrada</span>
  );
}

export function CollectionWorkspace({
  collectionId,
}: {
  collectionId?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const state = useMemo(() => parseCollectionQuery(search), [search]);
  const query = buildCollectionQuery(state);
  const [draft, setDraft] = useState(state);
  const [validation, setValidation] = useState("");
  const [now, setNow] = useState(Date.now());
  const [optionScope, setOptionScope] = useState({
    provider: state.provider,
    search: state.account_id,
  });

  const listPlaceholderIdentity = useMemo(
    () =>
      buildCollectionQuery({
        ...state,
        page: 1,
      }),
    [search],
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
    key: queryKeys.collections.options(
      optionScope.provider,
      optionScope.search,
      50,
    ),
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
  const optionsError = Boolean(optionsRequest.error);
  const loading = collectionId
    ? detailRequest.isLoading
    : listRequest.isLoading;
  const refreshing = collectionId
    ? detailRequest.isFetching && !detailRequest.isLoading
    : listRequest.isFetching && !listRequest.isLoading;
  const requestError = collectionId ? detailRequest.error : listRequest.error;
  const error = requestError
    ? requestError instanceof ApiError && requestError.status === 404
      ? "Coleta não encontrada."
      : collectionId
        ? "Não foi possível carregar a coleta."
        : "Não foi possível carregar as coletas."
    : "";

  const hasFilters = Boolean(
    state.provider ||
    state.account_id ||
    state.status ||
    state.date_from ||
    state.date_to ||
    state.analyzer_version,
  );
  const detailHref = (id: string) =>
    `/collections/${encodeURIComponent(id)}?${query}`;
  const change = (patch: Record<string, string | number>) =>
    router.push(`${pathname}?${patchCollectionQuery(search, patch)}`, {
      scroll: false,
    });
  useEffect(() => {
    setDraft(state);
    setValidation("");
  }, [state]);

  useEffect(() => {
    if (collectionId) return;
    const timer = window.setTimeout(() => {
      setOptionScope({
        provider: draft.provider,
        search: draft.account_id,
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [collectionId, draft.provider, draft.account_id]);

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

  const statusOptions = Object.entries(COLLECTION_STATUSES);
  return (
    <>
      <PageHeader
        eyebrow="OPERAÇÃO CLOUD"
        title={collectionId ? `Coleta #${collectionId.slice(0, 8)}` : "Coletas"}
        description="Execuções por cloud e conta, com histórico, resultados e falhas."
      />
      <div className="collection-toolbar">
        {collectionId && (
          <Link className="button ghost" href={`/collections?${query}`}>
            ← Voltar às coletas
          </Link>
        )}
        <span>
          Horários no fuso local do navegador · atualização a cada 15s apenas durante coletas em andamento
        </span>
        <button
          className="button ghost"
          disabled={loading || refreshing}
          onClick={() => {
            if (collectionId) void detailRequest.refetch();
            else {
              void listRequest.refetch();
              void optionsRequest.refetch();
            }
          }}
        >
          <RefreshCw size={16} /> Atualizar
        </button>
      </div>
      {!collectionId && (
        <form
          className="panel opportunity-filter-panel"
          onSubmit={(event) => {
            event.preventDefault();
            if (
              draft.date_from &&
              draft.date_to &&
              new Date(draft.date_from) >= new Date(draft.date_to)
            ) {
              setValidation("O início deve ser anterior ao fim do período.");
              return;
            }
            setValidation("");
            change({ ...draft, page: 1 });
          }}
        >
          <div className="opportunity-filter-heading">
            <strong>Filtros de coletas</strong>
            <button
              type="button"
              className="filter-clear"
              onClick={() => router.push("/collections")}
            >
              Limpar filtros
            </button>
          </div>
          <div className="opportunity-filter-grid">
            <label className="opportunity-filter">
              <span>Cloud</span>
              <div>
                <input
                  list="collection-providers"
                  placeholder="Todas as clouds"
                  value={draft.provider}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      provider: event.target.value,
                      account_id: "",
                    })
                  }
                />
              </div>
              <datalist id="collection-providers">
                {options.providers.map((provider) => (
                  <option key={provider} value={provider}>
                    {providerLabel(provider)}
                  </option>
                ))}
              </datalist>
            </label>
            <label className="opportunity-filter account-filter">
              <span>Conta · nome ou identificador</span>
              <div>
                <input
                  list="collection-accounts"
                  placeholder="Busque e selecione ou informe o ID"
                  value={draft.account_id}
                  onChange={(event) =>
                    setDraft({ ...draft, account_id: event.target.value })
                  }
                />
              </div>
              <datalist id="collection-accounts">
                {options.accounts.map((account) => (
                  <option
                    key={`${account.provider}:${account.account_id}`}
                    value={account.account_id}
                  >
                    {account.account_name || account.account_id} ·{" "}
                    {providerLabel(account.provider)} · {account.account_id}
                  </option>
                ))}
              </datalist>
              {options.has_more_accounts && (
                <small>Digite para buscar mais contas.</small>
              )}
            </label>
            <label className="opportunity-filter">
              <span>Status</span>
              <div>
                <select
                  aria-label="Status"
                  value={draft.status}
                  onChange={(event) =>
                    setDraft({ ...draft, status: event.target.value })
                  }
                >
                  <option value="">Todos</option>
                  {statusOptions.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            </label>
            <label className="opportunity-filter">
              <span>Início do período (inclusivo)</span>
              <div>
                <input
                  type="datetime-local"
                  value={localDateTime(draft.date_from)}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      date_from: event.target.value
                        ? new Date(event.target.value).toISOString()
                        : "",
                    })
                  }
                />
              </div>
            </label>
            <label className="opportunity-filter">
              <span>Fim do período (exclusivo)</span>
              <div>
                <input
                  type="datetime-local"
                  value={localDateTime(draft.date_to)}
                  onChange={(event) =>
                    setDraft({
                      ...draft,
                      date_to: event.target.value
                        ? new Date(event.target.value).toISOString()
                        : "",
                    })
                  }
                />
              </div>
            </label>
            <label className="opportunity-filter">
              <span>Versão dos analyzers</span>
              <div>
                <input
                  placeholder="Todas as versões"
                  value={draft.analyzer_version}
                  onChange={(event) =>
                    setDraft({ ...draft, analyzer_version: event.target.value })
                  }
                />
              </div>
            </label>
          </div>
          {optionsError && (
            <p role="status">
              Não foi possível carregar sugestões. Você ainda pode informar a
              cloud e o ID da conta.
            </p>
          )}
          {validation && (
            <p className="form-error" role="alert">
              {validation}
            </p>
          )}
          <div className="collection-toolbar">
            <button type="submit" className="button primary">
              Aplicar filtros
            </button>
            <button
              type="button"
              className="button ghost"
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
            </button>
          </div>
        </form>
      )}
      {error && (
        <div className="alert error" role="alert">
          {error}{" "}
          <button
            className="button ghost"
            onClick={() => {
              if (collectionId) void detailRequest.refetch();
              else void listRequest.refetch();
            }}
          >
            Tentar novamente
          </button>
        </div>
      )}
      {(loading || refreshing) && (
        <p role="status">
          {loading ? "Carregando coletas…" : "Atualizando coletas…"}
        </p>
      )}
      {!collectionId && data?.account_summary && (
        <section
          className="panel collection-account-summary"
          aria-label="Últimas coletas da conta"
        >
          <p>
            Contexto da conta/cloud selecionada, considerando todo o histórico.
          </p>
          <p>
            <strong>Última execução: </strong>
            <RunLink run={data.account_summary.latest_run} href={detailHref} />
          </p>
          <p>
            <strong>Última conclusão com sucesso: </strong>
            <RunLink
              run={data.account_summary.latest_success}
              href={detailHref}
            />
          </p>
          <small>Sucesso com avisos pode conter resultados incompletos.</small>
        </section>
      )}
      {!collectionId && (
        <section
          className="panel table-panel"
          aria-label="Histórico de coletas"
          aria-busy={loading}
        >
          <div className="panel-heading collection-toolbar">
            <h2>{data ? `${number(data.total)} coleta(s)` : "Histórico"}</h2>
            <label>
              Ordenar por{" "}
              <select
                aria-label="Ordenar por"
                value={state.sort}
                onChange={(event) => change({ sort: event.target.value })}
              >
                <option value="started_at">Início</option>
                <option value="opportunities_found">
                  Oportunidades encontradas
                </option>
              </select>
            </label>
            <label>
              Direção{" "}
              <select
                aria-label="Direção"
                value={state.order}
                onChange={(event) => change({ order: event.target.value })}
              >
                <option value="desc">Decrescente</option>
                <option value="asc">Crescente</option>
              </select>
            </label>
          </div>
          <div
            className="data-table-wrap"
            tabIndex={0}
            role="region"
            aria-label="Tabela de coletas"
          >
            <table className="data-table collection-table">
              <thead>
                <tr>
                  {[
                    "Início / fim",
                    "Cloud",
                    "Conta",
                    "Status",
                    "Duração",
                    "Recursos",
                    "Oportunidades encontradas",
                  ].map((label) => (
                    <th scope="col" key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!data &&
                  loading &&
                  Array.from({ length: 5 }, (_, row) => (
                    <tr key={row} aria-hidden="true">
                      {Array.from({ length: 7 }, (_, cell) => (
                        <td key={cell}>
                          <span className="skeleton-box skeleton-line" />
                        </td>
                      ))}
                    </tr>
                  ))}
                {data?.items.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link
                        className="collection-link"
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
                      <span>Fim: {formatDate(run.finished_at)}</span>
                      <code>{run.id.slice(0, 8)}</code>
                    </td>
                    <td>{providerLabel(run.provider)}</td>
                    <td>
                      <strong>{run.account_name || run.account_id}</strong>
                      {run.account_name && <span>{run.account_id}</span>}
                    </td>
                    <td>
                      <RunStatus run={run} />
                    </td>
                    <td>{durationLabel(run, now)}</td>
                    <td>
                      {run.resources_analyzed_available
                        ? number(run.resources_analyzed)
                        : "Não disponível"}
                    </td>
                    <td>
                      {run.status === "RUNNING"
                        ? "Aguardando conclusão"
                        : number(run.opportunities_found)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loading && !error && data && !data.items.length && (
            <div className="empty-table">
              <p>
                {hasFilters
                  ? "Nenhuma coleta encontrada para estes filtros."
                  : state.page > 1
                    ? "Nenhuma coleta nesta página."
                    : "Ainda não existem coletas."}
              </p>
              {hasFilters && (
                <button
                  className="button ghost"
                  onClick={() => router.push("/collections")}
                >
                  Limpar filtros
                </button>
              )}
            </div>
          )}
          <div className="collection-toolbar collection-pagination">
            <label>
              Por página{" "}
              <select
                aria-label="Por página"
                value={state.page_size}
                onChange={(event) =>
                  change({ page_size: Number(event.target.value) })
                }
              >
                {[25, 50, 100].map((size) => (
                  <option key={size}>{size}</option>
                ))}
              </select>
            </label>
            <span>
              Página {state.page} de {data?.total_pages || 1}
            </span>
            <button
              className="button ghost"
              disabled={loading || state.page <= 1}
              onClick={() => change({ page: state.page - 1 })}
            >
              Anterior
            </button>
            <button
              className="button ghost"
              disabled={loading || !data || state.page >= data.total_pages}
              onClick={() => change({ page: state.page + 1 })}
            >
              Próxima
            </button>
          </div>
          <p className="collection-note">
            Recursos: o coletor atual ainda não informa esse total.
            Oportunidades encontradas: total persistido ao concluir; confira as
            observações no detalhe.
          </p>
        </section>
      )}
      {collectionId && detail && (
        <section className="panel collection-detail" aria-busy={loading}>
          <div className="collection-toolbar">
            <h2>CollectionRun</h2>
            <RunStatus run={detail} />
          </div>
          <code className="collection-id">{detail.id}</code>
          {detail.detailed_observations_available ? (
            <CollectionComparisonActions run={detail} />
          ) : (
            <div className="alert" role="status">
              <strong>Detalhes históricos expirados.</strong>
              <p>
                O resumo desta CollectionRun foi preservado, mas as observações detalhadas
                já não estão disponíveis pela política de retenção.
              </p>
            </div>
          )}
          {detail.status === "FAILED" && (
            <div className="alert error" role="alert">
              <strong>Falha durante a coleta</strong>
              <p>
                {detail.error_detail || "O motivo da falha não foi registrado."}
              </p>
            </div>
          )}
          {detail.has_warnings && (
            <div className="alert" role="status">
              <strong>
                Concluída com avisos: resultados podem estar incompletos.
              </strong>
              <p>
                {detail.warning_detail ||
                  "Um ou mais analyzers não concluíram a coleta."}
              </p>
            </div>
          )}
          {detail.status === "RUNNING" && (
            <p role="status">
              {durationLabel(detail, now)}. As métricas finais ainda não estão
              disponíveis.
            </p>
          )}
          <dl className="collection-metadata">
            <div>
              <dt>Cloud</dt>
              <dd>{providerLabel(detail.provider)}</dd>
            </div>
            <div>
              <dt>Conta</dt>
              <dd>
                {detail.account_name || detail.account_id}
                {detail.account_name && <small>{detail.account_id}</small>}
              </dd>
            </div>
            <div>
              <dt>Início</dt>
              <dd>{preciseDate(detail.started_at)}</dd>
            </div>
            <div>
              <dt>Fim</dt>
              <dd>{preciseDate(detail.finished_at)}</dd>
            </div>
            <div>
              <dt>Duração</dt>
              <dd>{durationLabel(detail, now)}</dd>
            </div>
            <div>
              <dt>Versão dos analyzers</dt>
              <dd>{detail.analyzer_version || "Não registrada"}</dd>
            </div>
            {detail.trigger && (
              <div>
                <dt>Gatilho</dt>
                <dd>
                  {detail.trigger === "manual"
                    ? "Manual"
                    : detail.trigger === "scheduled"
                      ? "Agendada"
                      : detail.trigger}
                </dd>
              </div>
            )}
            {detail.scan_id && (
              <div>
                <dt>Scan de origem</dt>
                <dd>
                  <code>{detail.scan_id}</code>
                </dd>
              </div>
            )}
            <div>
              <dt>Recursos analisados</dt>
              <dd>
                {detail.resources_analyzed_available
                  ? number(detail.resources_analyzed)
                  : "Não disponível"}
              </dd>
            </div>
            <div>
              <dt>Oportunidades encontradas</dt>
              <dd>
                {detail.status === "RUNNING"
                  ? "Aguardando conclusão"
                  : number(detail.opportunities_found)}
              </dd>
            </div>
            <div>
              <dt>Detalhes de observação retidos</dt>
              <dd>{number(detail.opportunities_observed)}</dd>
            </div>
          </dl>
          <p>
            O total encontrado é persistido na CollectionRun. A contagem de detalhes
            retidos representa apenas observations ainda disponíveis no banco; o total
            de recursos ainda não é medido pelo coletor atual.
          </p>
          {detail.detailed_observations_available ? (
            <>
              <Link className="button primary" href={collectionOpportunitiesUrl(detail.id)}>
                Ver oportunidades desta coleta
              </Link>
              <p className="collection-note">
                A tela abre na aba Abertas. Use também Tratadas e Rejeitadas; o
                filtro desta coleta permanece aplicado. As evidências históricas
                estão no detalhe de cada oportunidade.
              </p>
            </>
          ) : (
            <p className="collection-note">
              A listagem detalhada desta coleta não é exibida porque a ausência de
              observations expiradas não significa que a coleta encontrou zero oportunidades.
            </p>
          )}
        </section>
      )}
    </>
  );
}
