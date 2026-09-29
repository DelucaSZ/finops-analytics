"use client";

import Link from "next/link";
import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ArrowRight,
  Building2,
  CheckCircle2,
  CircleDollarSign,
  Cloud,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  XCircle,
} from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/lib/api";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import {
  buildDashboardApiQuery,
  parseDashboardSearchParams,
  patchDashboardUrl,
  scopedDashboardHref,
} from "@/lib/dashboard-query.mjs";
import type { DashboardQueryState } from "@/lib/dashboard-query.mjs";
import type {
  CollectionOptions,
  DashboardCollectionHealth,
  DashboardSummary,
} from "@/lib/types";

function DashboardBoot() {
  return (
    <>
      <PageHeader
        eyebrow="FINOPS OPERACIONAL"
        title="Visão Geral"
        description="Carregando o estado consolidado das últimas coletas válidas."
      />
      <section className="dashboard-scope-panel panel" aria-hidden="true">
        <span className="skeleton-box skeleton-line" />
      </section>
      <section className="metrics-grid dashboard-kpis" aria-hidden="true">
        {Array.from({ length: 6 }, (_, index) => (
          <article className="metric-card" key={index}>
            <span className="skeleton-box skeleton-title" />
            <span className="skeleton-box skeleton-line" />
          </article>
        ))}
      </section>
    </>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<DashboardBoot />}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<DashboardQueryState>(
    () => parseDashboardSearchParams(searchKey),
    [searchKey],
  );
  const apiQuery = useMemo(
    () => buildDashboardApiQuery(state),
    [state.accountId, state.provider],
  );

  const optionsQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "100" });
    if (state.provider) params.set("provider", state.provider);
    return params.toString();
  }, [state.provider]);

  const summaryRequest = useApiQuery<DashboardSummary>({
    key: queryKeys.dashboard.summary(state.provider, state.accountId),
    path: `/dashboard/summary${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.operational,
  });
  const healthRequest = useApiQuery<DashboardCollectionHealth>({
    key: queryKeys.dashboard.health(state.provider, state.accountId),
    path: `/dashboard/collection-health${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.operational,
  });
  const optionsRequest = useApiQuery<CollectionOptions>({
    key: queryKeys.collections.options(state.provider, "", 100),
    path: `/collections/options?${optionsQuery}`,
    ...cachePolicy.metadata,
  });

  const summary = summaryRequest.data ?? null;
  const health = healthRequest.data ?? null;
  const options = optionsRequest.data ?? {
    providers: [],
    accounts: [],
    has_more_accounts: false,
  };
  const summaryLoading = summaryRequest.isLoading;
  const healthLoading = healthRequest.isLoading;
  const optionsLoading = optionsRequest.isLoading;
  const summaryError = summaryRequest.error?.message || "";
  const healthError = healthRequest.error?.message || "";
  const optionsError = optionsRequest.error?.message || "";

  function updateScope(patch: Record<string, string | null>) {
    const params = patchDashboardUrl(searchKey, patch);
    router.replace(`/${params.size ? `?${params.toString()}` : ""}`, {
      scroll: false,
    });
  }

  const selectedAccountKey =
    state.provider && state.accountId
      ? `${state.provider}|${state.accountId}`
      : "";

  const selectedAccount = options.accounts.find(
    (account) =>
      account.provider === state.provider &&
      account.account_id === state.accountId,
  );

  const scopeDescription = state.accountId
    ? `${selectedAccount?.account_name || state.accountId} · ${providerLabel(state.provider)}`
    : state.provider
      ? `${providerLabel(state.provider)} · todas as contas`
      : "Todas as clouds · todas as contas";

  const currentOpportunityHref = (
    extra: Record<string, string | number | null | undefined> = {},
  ) =>
    scopedDashboardHref("/opportunities", state, {
      current: "true",
      ...extra,
    });

  const monthlyTotals = summary?.financial.totals || [];
  const failedCollectionsHref = scopedDashboardHref("/collections", state, {
    status: "FAILED",
  });
  const collectionsHref = scopedDashboardHref("/collections", state);

  const noRuns =
    !healthLoading && !healthError && health && health.total_scopes === 0;
  const noValidData =
    !summaryLoading &&
    !summaryError &&
    summary &&
    !summary.scope.has_current_data &&
    health &&
    health.total_scopes > 0;

  return (
    <>
      <PageHeader
        eyebrow="FINOPS OPERACIONAL"
        title="Visão Geral"
        description="Estado atual consolidado por cloud e conta, com investigação direta de oportunidades e coletas."
        actions={
          <button
            className="button ghost"
            type="button"
            onClick={() => {
              void summaryRequest.refetch();
              void healthRequest.refetch();
              void optionsRequest.refetch();
            }}
            disabled={
              summaryRequest.isFetching ||
              healthRequest.isFetching ||
              optionsRequest.isFetching
            }
          >
            <RefreshCw
              size={16}
              className={
                summaryRequest.isFetching || healthRequest.isFetching
                  ? "spin"
                  : ""
              }
            />
            Atualizar
          </button>
        }
      />

      <section className="panel dashboard-scope-panel" aria-label="Escopo global">
        <div className="dashboard-scope-copy">
          <span className="eyebrow">ESCOPO ATUAL</span>
          <strong>{scopeDescription}</strong>
          <p>Dados consolidados das últimas coletas concluídas com sucesso de cada cloud/conta.</p>
        </div>
        <div className="dashboard-scope-controls">
          <label>
            <span>Cloud</span>
            <select
              aria-label="Cloud"
              value={state.provider}
              disabled={optionsLoading}
              onChange={(event) =>
                updateScope({
                  provider: event.target.value || null,
                  account_id: null,
                })
              }
            >
              <option value="">Todas as clouds</option>
              {options.providers.map((provider) => (
                <option value={provider} key={provider}>
                  {providerLabel(provider)}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Conta</span>
            <select
              aria-label="Conta"
              value={selectedAccountKey}
              disabled={optionsLoading}
              onChange={(event) => {
                if (!event.target.value) {
                  updateScope({ account_id: null });
                  return;
                }
                const separator = event.target.value.indexOf("|");
                updateScope({
                  provider: event.target.value.slice(0, separator),
                  account_id: event.target.value.slice(separator + 1),
                });
              }}
            >
              <option value="">Todas as contas</option>
              {options.accounts.map((account) => (
                <option
                  key={`${account.provider}:${account.account_id}`}
                  value={`${account.provider}|${account.account_id}`}
                >
                  {account.account_name || account.account_id}
                  {state.provider ? "" : ` · ${providerLabel(account.provider)}`}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="dashboard-freshness">
          {healthLoading ? (
            <span className="skeleton-box skeleton-line" aria-label="Carregando atualização" />
          ) : healthError ? (
            <span className="dashboard-inline-error">Freshness indisponível</span>
          ) : health?.newest_valid_at ? (
            <>
              <span>
                Mais recente <strong>{formatDate(health.newest_valid_at)}</strong>
              </span>
              <span>
                Dado mais antigo <strong>{formatDate(health.oldest_valid_at)}</strong>
              </span>
            </>
          ) : (
            <span>Sem coleta válida neste escopo.</span>
          )}
        </div>
      </section>

      {optionsError && (
        <div className="alert error" role="alert">
          {optionsError}
        </div>
      )}
      {options.has_more_accounts && (
        <div className="alert" role="status">
          O seletor mostra as primeiras 100 contas deste escopo. Use a tela de Coletas para pesquisar outras contas.
        </div>
      )}

      {noRuns && (
        <section className="panel dashboard-empty-state">
          <Sparkles size={28} />
          <h2>Ainda não existem dados suficientes para montar a visão geral.</h2>
          <p>Execute uma coleta para iniciar a análise operacional do DeepOps.</p>
          <Link className="button primary" href="/accounts">
            Ir para contas <ArrowRight size={16} />
          </Link>
        </section>
      )}

      {noValidData && (
        <div className="alert error" role="alert">
          Existem execuções neste escopo, mas nenhuma coleta concluída com sucesso está disponível para representar o estado atual. Consulte a saúde das coletas abaixo.
        </div>
      )}

      {summaryError && (
        <div className="alert error dashboard-section-error" role="alert">
          <div>
            <strong>Não foi possível carregar os indicadores.</strong>
            <span>{summaryError}</span>
          </div>
          <button
            className="button ghost"
            type="button"
            onClick={() => void summaryRequest.refetch()}
          >
            Tentar novamente
          </button>
        </div>
      )}

      {!noRuns && (summaryLoading || summary?.scope.has_current_data) && (
        <>
          <section className="metrics-grid dashboard-kpis" aria-label="Indicadores principais">
            <KpiCard
              loading={summaryLoading}
              icon={<Activity size={20} />}
              label="Oportunidades abertas"
              value={summary?.opportunities.open ?? 0}
              detail="OPEN no estado atual consolidado"
              href={currentOpportunityHref({ status: "open" })}
            />
            <KpiCard
              loading={summaryLoading}
              icon={<CircleDollarSign size={20} />}
              label="Economia potencial"
              value={
                monthlyTotals.length
                  ? monthlyTotals
                      .map((total) => formatMoney(total.amount, total.currency))
                      .join(" · ")
                  : "—"
              }
              detail={
                monthlyTotals.length
                  ? "estimated_monthly_savings por mês"
                  : "Sem métrica financeira agregável"
              }
              href={currentOpportunityHref({
                status: "open",
                sort: "estimated_savings",
                order: "desc",
              })}
              featured
            />
            <KpiCard
              loading={summaryLoading}
              icon={<Sparkles size={20} />}
              label="Novas desde a coleta anterior"
              value={summary?.opportunities.new_since_previous ?? 0}
              detail="Somente contas com baseline comparável"
              href={collectionsHref}
            />
            <KpiCard
              loading={summaryLoading}
              icon={<CheckCircle2 size={20} />}
              label="Tratadas"
              value={summary?.opportunities.treated ?? 0}
              detail="Lifecycle TREATED no estado atual"
              href={currentOpportunityHref({ status: "treated" })}
            />
            <KpiCard
              loading={summaryLoading}
              icon={<XCircle size={20} />}
              label="Rejeitadas"
              value={summary?.opportunities.rejected ?? 0}
              detail="Lifecycle REJECTED no estado atual"
              href={currentOpportunityHref({ status: "rejected" })}
            />
            <KpiCard
              loading={healthLoading}
              icon={<TriangleAlert size={20} />}
              label="Falhas na última execução"
              value={health?.latest_execution.failed ?? 0}
              detail={
                health?.latest_execution.running
                  ? `${health.latest_execution.running} coleta(s) em andamento`
                  : "Última execução por cloud/conta"
              }
              href={failedCollectionsHref}
            />
          </section>

          <section className="dashboard-operational-grid">
            <article className="panel dashboard-severity-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">ESTADO ATUAL</span>
                  <h2>Oportunidades por severidade</h2>
                </div>
                <Link href={currentOpportunityHref({ status: "open" })}>
                  Ver abertas <ArrowRight size={15} />
                </Link>
              </div>
              {summaryLoading ? (
                <SectionSkeleton rows={3} />
              ) : (
                <SeverityBreakdown
                  summary={summary}
                  hrefFor={(severity) =>
                    currentOpportunityHref({ status: "open", severity })
                  }
                />
              )}
            </article>

            <article className="panel dashboard-distribution-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">CONCENTRAÇÃO</span>
                  <h2>Clouds e contas</h2>
                </div>
              </div>
              {summaryLoading ? (
                <SectionSkeleton rows={4} />
              ) : (
                <Distribution summary={summary} state={state} />
              )}
            </article>
          </section>

          <section className="dashboard-operational-grid dashboard-secondary-grid">
            <article className="panel dashboard-top-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">MAIOR IMPACTO FINANCEIRO</span>
                  <h2>Oportunidades abertas para atenção</h2>
                </div>
                <Link
                  href={currentOpportunityHref({
                    status: "open",
                    sort: "estimated_savings",
                    order: "desc",
                  })}
                >
                  Ver todas <ArrowRight size={15} />
                </Link>
              </div>
              {summaryLoading ? (
                <SectionSkeleton rows={5} />
              ) : summary?.top_opportunities.length ? (
                <div className="dashboard-top-list">
                  {summary.top_opportunities.map((item) => (
                    <Link
                      key={item.id}
                      className="dashboard-top-row"
                      href={scopedDashboardHref(
                        "/opportunities",
                        {
                          provider: item.provider,
                          accountId: item.account_id,
                        },
                        {
                          current: "true",
                          status: "open",
                          opportunity_id: item.id,
                        },
                      )}
                    >
                      <div>
                        <strong>{item.title}</strong>
                        <span>
                          {item.resource_name || item.resource_id} · {item.region || "Sem região"}
                        </span>
                        <small>
                          {item.account_name || item.account_id} · {providerLabel(item.provider)}
                        </small>
                      </div>
                      <StatusBadge value={item.severity} />
                      <strong className="dashboard-money">
                        {formatMoney(item.estimated_monthly_savings, item.currency)}/mês
                      </strong>
                    </Link>
                  ))}
                </div>
              ) : (
                <EmptyBlock
                  title="Nenhuma oportunidade aberta encontrada neste escopo."
                  text="Há coleta válida, mas nenhuma oportunidade OPEN observada na coleta atual."
                />
              )}
            </article>

            <article className="panel dashboard-change-panel">
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">COMPARAÇÃO</span>
                  <h2>Desde as últimas coletas</h2>
                </div>
                <Link href={collectionsHref}>
                  Investigar <ArrowRight size={15} />
                </Link>
              </div>
              {summaryLoading ? (
                <SectionSkeleton rows={4} />
              ) : summary ? (
                <>
                  <div className="dashboard-change-stats">
                    <div>
                      <strong>+{summary.recent_changes.new}</strong>
                      <span>novas</span>
                    </div>
                    <div>
                      <strong>{summary.recent_changes.no_longer_detected}</strong>
                      <span>não detectadas novamente</span>
                    </div>
                    <div>
                      <strong>{summary.recent_changes.comparable_scopes}</strong>
                      <span>escopos comparáveis</span>
                    </div>
                  </div>
                  {summary.recent_changes.scopes_without_baseline > 0 && (
                    <p className="dashboard-note">
                      {summary.recent_changes.scopes_without_baseline} escopo(s) ainda sem baseline; a primeira coleta não é contada como “nova”.
                    </p>
                  )}
                  {(summary.recent_changes.rules_version_changed_scopes > 0 ||
                    summary.recent_changes.rules_version_unknown_scopes > 0) && (
                    <div className="dashboard-warning-note">
                      <TriangleAlert size={16} />
                      <span>
                        Versão de regras diferente em {summary.recent_changes.rules_version_changed_scopes} escopo(s) e não registrada em {summary.recent_changes.rules_version_unknown_scopes} escopo(s). Os números continuam comparando observations, mas exigem contexto.
                      </span>
                    </div>
                  )}
                  {!summary.recent_changes.changed_available && (
                    <p className="dashboard-note">
                      “Alteradas” não é aproximado aqui. A Etapa 8 calcula CHANGED por diff semântico das evidências na comparação de cada coleta.
                    </p>
                  )}
                </>
              ) : null}
            </article>
          </section>
        </>
      )}

      {!noRuns && (
        <section className="panel dashboard-health-panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">SAÚDE DAS COLETAS</span>
              <h2>Última execução x última coleta válida</h2>
            </div>
            <Link href={collectionsHref}>
              Ver coletas <ArrowRight size={15} />
            </Link>
          </div>

          {healthError ? (
            <div className="dashboard-widget-error" role="alert">
              <TriangleAlert size={18} />
              <div>
                <strong>Não foi possível carregar a saúde das coletas.</strong>
                <p>{healthError}</p>
              </div>
              <button
                className="button ghost"
                type="button"
                onClick={() => void healthRequest.refetch()}
              >
                Tentar novamente
              </button>
            </div>
          ) : healthLoading ? (
            <SectionSkeleton rows={4} />
          ) : health ? (
            <>
              <div className="dashboard-health-summary">
                <span>
                  <CheckCircle2 size={16} />
                  {health.valid_scopes} com coleta válida
                </span>
                <Link href={failedCollectionsHref}>
                  <XCircle size={16} />
                  {health.latest_execution.failed} com última execução falha
                </Link>
                <span>
                  <RefreshCw size={16} />
                  {health.latest_execution.running} em andamento
                </span>
                {health.valid_with_warnings > 0 && (
                  <span>
                    <TriangleAlert size={16} />
                    {health.valid_with_warnings} concluída(s) com avisos
                  </span>
                )}
              </div>

              <div className="dashboard-health-table-wrap" tabIndex={0} role="region" aria-label="Últimas coletas por conta">
                <table className="data-table dashboard-health-table">
                  <thead>
                    <tr>
                      <th scope="col">Cloud / conta</th>
                      <th scope="col">Última execução</th>
                      <th scope="col">Última coleta válida</th>
                    </tr>
                  </thead>
                  <tbody>
                    {health.items.map((item) => (
                      <tr key={`${item.provider}:${item.account_id}`}>
                        <td>
                          <strong>{item.account_name || item.account_id}</strong>
                          <span>{providerLabel(item.provider)} · {item.account_id}</span>
                        </td>
                        <td>
                          <Link href={`/collections/${encodeURIComponent(item.latest_execution.id)}`}>
                            <StatusBadge value={item.latest_execution.status} />
                          </Link>
                          <span>{formatDate(item.latest_execution.started_at)}</span>
                          {item.latest_execution.has_warnings && <small>Com avisos</small>}
                        </td>
                        <td>
                          {item.latest_valid ? (
                            <>
                              <Link href={`/collections/${encodeURIComponent(item.latest_valid.id)}`}>
                                {formatDate(item.latest_valid.started_at)}
                              </Link>
                              {item.latest_valid.has_warnings && <small>Concluída com avisos</small>}
                            </>
                          ) : (
                            <strong className="dashboard-missing-valid">Sem coleta válida</strong>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {!health.stale_policy_configured && (
                <p className="dashboard-note">
                  O DeepOps ainda não possui uma política persistida de atraso de coleta; por isso a Home não inventa um threshold de “atrasada”. Freshness é exibida pelos horários reais.
                </p>
              )}
            </>
          ) : null}
        </section>
      )}
    </>
  );
}

function KpiCard({
  loading,
  icon,
  label,
  value,
  detail,
  href,
  featured = false,
}: {
  loading: boolean;
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  detail: string;
  href: string;
  featured?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`metric-card dashboard-kpi-link${featured ? " featured" : ""}`}
      aria-label={`${label}: ${typeof value === "string" || typeof value === "number" ? value : ""}. Abrir investigação.`}
    >
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      {loading ? (
        <span className="skeleton-box skeleton-title" aria-hidden="true" />
      ) : (
        <strong>{value}</strong>
      )}
      <small>{detail}</small>
      <ArrowRight size={15} className="dashboard-kpi-arrow" />
    </Link>
  );
}

function SectionSkeleton({ rows }: { rows: number }) {
  return (
    <div className="dashboard-section-skeleton" aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <span className="skeleton-box skeleton-line" key={index} />
      ))}
    </div>
  );
}

function EmptyBlock({ title, text }: { title: string; text: string }) {
  return (
    <div className="empty-state dashboard-inline-empty">
      <Sparkles size={22} />
      <strong>{title}</strong>
      <p>{text}</p>
    </div>
  );
}

function SeverityBreakdown({
  summary,
  hrefFor,
}: {
  summary: DashboardSummary | null;
  hrefFor: (severity: string) => string;
}) {
  if (!summary) return null;
  const items = [
    ["high", "Alta", summary.severity.high],
    ["medium", "Média", summary.severity.medium],
    ["low", "Baixa", summary.severity.low],
  ] as const;
  const total = Math.max(summary.opportunities.open, 1);
  return (
    <div className="dashboard-severity-list">
      {items.map(([severity, label, value]) => (
        <Link href={hrefFor(severity)} key={severity} className="dashboard-severity-row">
          <div>
            <span className={`severity-dot ${severity}`} aria-hidden="true" />
            <strong>{label}</strong>
            <span>{value} oportunidade(s)</span>
          </div>
          <div className="dashboard-bar-track" aria-hidden="true">
            <span
              className={`dashboard-bar-fill ${severity}`}
              style={{ width: `${value ? Math.max(6, (value / total) * 100) : 0}%` }}
            />
          </div>
          <ArrowRight size={15} />
        </Link>
      ))}
      {summary.severity.other > 0 && (
        <p className="dashboard-note">
          {summary.severity.other} oportunidade(s) possuem severidade fora de HIGH/MEDIUM/LOW e não foram reclassificadas pela Home.
        </p>
      )}
    </div>
  );
}

function Distribution({
  summary,
  state,
}: {
  summary: DashboardSummary | null;
  state: DashboardQueryState;
}) {
  if (!summary) return null;
  return (
    <div className="dashboard-distributions">
      <div>
        <h3>Por cloud</h3>
        {summary.by_provider.length ? (
          <div className="dashboard-ranked-list">
            {summary.by_provider.map((item) => (
              <Link
                href={scopedDashboardHref(
                  "/opportunities",
                  { provider: item.provider, accountId: "" },
                  { current: "true", status: "open" },
                )}
                key={item.provider}
              >
                <span><Cloud size={15} /> {providerLabel(item.provider)}</span>
                <strong>{item.open}</strong>
              </Link>
            ))}
          </div>
        ) : (
          <span className="dashboard-muted">Sem oportunidades abertas.</span>
        )}
      </div>
      <div>
        <h3>Top contas por oportunidades abertas</h3>
        {summary.by_account.length ? (
          <div className="dashboard-ranked-list">
            {summary.by_account.map((item) => (
              <Link
                href={scopedDashboardHref(
                  "/opportunities",
                  { provider: item.provider, accountId: item.account_id },
                  { current: "true", status: "open" },
                )}
                key={`${item.provider}:${item.account_id}`}
              >
                <span>
                  <Building2 size={15} />
                  {item.account_name || item.account_id}
                  <small>{providerLabel(item.provider)}</small>
                </span>
                <strong>{item.open}</strong>
              </Link>
            ))}
          </div>
        ) : (
          <span className="dashboard-muted">Sem oportunidades abertas.</span>
        )}
        {summary.by_account.length >= 8 && (
          <Link
            className="dashboard-more-link"
            href={scopedDashboardHref("/opportunities", state, {
              current: "true",
              status: "open",
            })}
          >
            Ver todas <ArrowRight size={14} />
          </Link>
        )}
      </div>
    </div>
  );
}
