"use client";

import Link from "next/link";
import { useMemo } from "react";
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
  Wrench,
  XCircle,
} from "lucide-react";
import { DashboardOperationalInsights as CollectionFailureOperationalInsights } from "@/components/dashboard-operational-insights";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/lib/api";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import {
  buildDashboardApiQuery,
  parseDashboardSearchParams,
  patchDashboardUrl,
  scopedDashboardHref,
} from "@/lib/dashboard-query.mjs";
import type { DashboardQueryState } from "@/lib/dashboard-query.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import type { CollectionOptions, DashboardSummary } from "@/lib/types";

type MoneyTotal = { currency: string; amount: string };
type ExecutiveDashboardSummary = Omit<
  DashboardSummary,
  "severity" | "by_provider" | "by_account" | "top_opportunities"
> & {
  data_updated_at: string | null;
  severity: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    other: number;
  };
  by_provider: Array<{
    provider: string;
    open: number;
    savings: MoneyTotal[];
  }>;
  by_account: Array<{
    provider: string;
    account_id: string;
    account_name: string | null;
    open: number;
    savings: MoneyTotal[];
  }>;
  by_service: Array<{
    service: string;
    open: number;
    savings: MoneyTotal[];
  }>;
  by_rule: Array<{
    rule_key: string;
    open: number;
    savings: MoneyTotal[];
  }>;
  top_opportunities: Array<{
    id: string;
    title: string;
    rule_key: string;
    service: string | null;
    resource_id: string;
    resource_name: string | null;
    region: string | null;
    provider: string;
    account_id: string;
    account_name: string | null;
    collection_run_id: string;
    severity: string;
    estimated_monthly_savings: string;
    currency: string;
  }>;
};

export function DashboardBoot() {
  return (
    <>
      <PageHeader
        eyebrow="FINOPS"
        title="Visão Geral"
        description="Carregando o potencial de otimização do ambiente."
      />
      <section className="dashboard-scope-panel panel" aria-hidden="true">
        <span className="skeleton-box skeleton-line" />
      </section>
      <section className="metrics-grid dashboard-kpis" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <article className="metric-card" key={index}>
            <span className="skeleton-box skeleton-title" />
            <span className="skeleton-box skeleton-line" />
          </article>
        ))}
      </section>
    </>
  );
}

export function ExecutiveDashboard() {
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

  const summaryRequest = useApiQuery<ExecutiveDashboardSummary>({
    key: queryKeys.dashboard.summary(state.provider, state.accountId),
    path: `/dashboard/summary${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.operational,
  });
  const optionsRequest = useApiQuery<CollectionOptions>({
    key: queryKeys.collections.options(state.provider, "", 100),
    path: `/collections/options?${optionsQuery}`,
    ...cachePolicy.metadata,
  });

  const summary = summaryRequest.data ?? null;
  const options = optionsRequest.data ?? {
    providers: [],
    accounts: [],
    has_more_accounts: false,
  };
  const summaryLoading = summaryRequest.isLoading;
  const optionsLoading = optionsRequest.isLoading;
  const summaryError = summaryRequest.error?.message || "";
  const optionsError = optionsRequest.error?.message || "";

  function updateScope(patch: Record<string, string | null>) {
    const params = patchDashboardUrl(searchKey, patch);
    router.replace(`/${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  }

  const selectedAccountKey =
    state.provider && state.accountId ? `${state.provider}|${state.accountId}` : "";
  const selectedAccount = options.accounts.find(
    (account) =>
      account.provider === state.provider && account.account_id === state.accountId,
  );
  const scopeDescription = state.accountId
    ? `${selectedAccount?.account_name || state.accountId} · ${providerLabel(state.provider)}`
    : state.provider
      ? `${providerLabel(state.provider)} · todas as contas`
      : "Todas as clouds · todas as contas";

  const opportunityHref = (
    extra: Record<string, string | number | null | undefined> = {},
  ) =>
    scopedDashboardHref("/opportunities", state, {
      current: "true",
      ...extra,
    });

  const totals = summary?.financial.totals || [];
  const hasBacklog = Boolean(summary?.opportunities.open);

  return (
    <>
      <PageHeader
        eyebrow="FINOPS"
        title="Visão Geral"
        description="Potencial atual de otimização, concentração de savings e principais oportunidades do ambiente."
        actions={
          <button
            className="button ghost"
            type="button"
            onClick={() => {
              void summaryRequest.refetch();
              void optionsRequest.refetch();
            }}
            disabled={summaryRequest.isFetching || optionsRequest.isFetching}
          >
            <RefreshCw
              size={16}
              className={summaryRequest.isFetching ? "spin" : ""}
            />
            Atualizar
          </button>
        }
      />

      <section className="panel dashboard-scope-panel" aria-label="Escopo global">
        <div className="dashboard-scope-copy">
          <span className="eyebrow">ESCOPO ATUAL</span>
          <strong>{scopeDescription}</strong>
          <p>Todos os indicadores abaixo respeitam este mesmo escopo.</p>
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
          {summaryLoading ? (
            <span className="skeleton-box skeleton-line" aria-label="Carregando atualização" />
          ) : summary?.data_updated_at ? (
            <span>
              Dados atualizados até <strong>{formatDate(summary.data_updated_at)}</strong>
            </span>
          ) : (
            <span>Sem referência de atualização para este escopo.</span>
          )}
        </div>
      </section>

      <DashboardOperationalInsights />

      {optionsError && (
        <div className="alert error" role="alert">
          {optionsError}
        </div>
      )}
      {options.has_more_accounts && (
        <div className="alert" role="status">
          O seletor mostra as primeiras 100 contas. Os indicadores continuam considerando todo o escopo selecionado.
        </div>
      )}

      {summaryError && (
        <div className="alert error dashboard-section-error" role="alert">
          <div>
            <strong>Não foi possível carregar o Dashboard.</strong>
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

      {!summaryError && (
        <>
          <section className="metrics-grid dashboard-kpis" aria-label="Indicadores executivos">
            <KpiCard
              loading={summaryLoading}
              icon={<Activity size={20} />}
              label="Oportunidades em aberto"
              value={summary?.opportunities.open ?? 0}
              detail="Backlog OPEN atual e não arquivado"
              href={opportunityHref({ status: "open" })}
            />
            <KpiCard
              loading={summaryLoading}
              icon={<CircleDollarSign size={20} />}
              label="Economia potencial"
              value={<SavingsValues totals={totals} />}
              detail="Saving mensal acionável, sem converter moedas"
              href={opportunityHref({
                status: "open",
                sort: "estimated_savings",
                order: "desc",
              })}
              featured
            />
            <KpiCard
              loading={summaryLoading}
              icon={<Sparkles size={20} />}
              label="Novas vs coleta anterior"
              value={summary?.opportunities.new_since_previous ?? 0}
              detail="Indicador comparativo; navegação será refinada na 24.12"
            />
            <KpiCard
              loading={summaryLoading}
              icon={<CheckCircle2 size={20} />}
              label="Tratadas no estado atual"
              value={summary?.opportunities.treated ?? 0}
              detail="Lifecycle TREATED no escopo corrente"
              href={opportunityHref({ status: "treated" })}
            />
            <KpiCard
              loading={summaryLoading}
              icon={<XCircle size={20} />}
              label="Rejeitadas no estado atual"
              value={summary?.opportunities.rejected ?? 0}
              detail="Não entram na economia potencial acionável"
              href={opportunityHref({ status: "rejected" })}
            />
          </section>

          {!summaryLoading && summary && !hasBacklog ? (
            <section className="panel dashboard-empty-state">
              <Sparkles size={28} />
              <h2>Nenhuma oportunidade em aberto no escopo atual.</h2>
              <p>O Dashboard permanece limpo quando não existe backlog operacional acionável.</p>
            </section>
          ) : (
            <>
              <section className="dashboard-operational-grid">
                <article className="panel dashboard-severity-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">CRITICIDADE</span>
                      <h2>Oportunidades por severidade</h2>
                    </div>
                    <Link href={opportunityHref({ status: "open" })}>
                      Ver abertas <ArrowRight size={15} />
                    </Link>
                  </div>
                  {summaryLoading ? (
                    <SectionSkeleton rows={4} />
                  ) : (
                    <SeverityBreakdown summary={summary} state={state} />
                  )}
                </article>

                <article className="panel dashboard-distribution-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">CLOUD</span>
                      <h2>Distribuição por provider</h2>
                    </div>
                  </div>
                  {summaryLoading ? (
                    <SectionSkeleton rows={4} />
                  ) : (
                    <ProviderDistribution summary={summary} />
                  )}
                </article>
              </section>

              <section className="dashboard-operational-grid dashboard-secondary-grid">
                <article className="panel dashboard-distribution-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">CONCENTRAÇÃO</span>
                      <h2>Contas com maior backlog</h2>
                    </div>
                    <Link href={opportunityHref({ status: "open" })}>
                      Ver todas <ArrowRight size={15} />
                    </Link>
                  </div>
                  {summaryLoading ? (
                    <SectionSkeleton rows={5} />
                  ) : (
                    <AccountRanking summary={summary} />
                  )}
                </article>

                <article className="panel dashboard-distribution-panel">
                  <div className="panel-heading">
                    <div>
                      <span className="eyebrow">ORIGEM DO SAVING</span>
                      <h2>Top serviços e regras</h2>
                    </div>
                  </div>
                  {summaryLoading ? (
                    <SectionSkeleton rows={5} />
                  ) : (
                    <ServiceRuleRanking summary={summary} state={state} />
                  )}
                </article>
              </section>

              <section className="panel dashboard-top-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">MAIOR IMPACTO</span>
                    <h2>Maiores oportunidades</h2>
                  </div>
                  <Link
                    href={opportunityHref({
                      status: "open",
                      sort: "estimated_savings",
                      order: "desc",
                    })}
                  >
                    Ver todas <ArrowRight size={15} />
                  </Link>
                </div>
                {summaryLoading ? (
                  <SectionSkeleton rows={6} />
                ) : summary?.top_opportunities.length ? (
                  <div className="dashboard-top-list">
                    {summary.top_opportunities.map((item) => (
                      <Link
                        key={item.id}
                        className="dashboard-top-row"
                        href={scopedDashboardHref(
                          "/opportunities",
                          { provider: item.provider, accountId: item.account_id },
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
                            {item.service || item.rule_key} · {item.resource_name || item.resource_id}
                          </span>
                          <small>
                            {item.account_name || item.account_id} · {providerLabel(item.provider)}
                            {item.region ? ` · ${item.region}` : ""}
                          </small>
                        </div>
                        <StatusBadge value={item.severity} />
                        <strong className="dashboard-money">
                          {formatMoney(item.estimated_monthly_savings, item.currency)}/mês
                        </strong>
                      </Link>
                    ))}
                  </div>
                ) : null}
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}

export function DashboardOperationalInsights() {
  return <CollectionFailureOperationalInsights />;
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
  href?: string;
  featured?: boolean;
}) {
  const content = (
    <>
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      {loading ? (
        <span className="skeleton-box skeleton-title" aria-hidden="true" />
      ) : (
        <strong>{value}</strong>
      )}
      <small>{detail}</small>
      {href ? <ArrowRight size={15} className="dashboard-kpi-arrow" /> : null}
    </>
  );
  if (!href) {
    return <article className={`metric-card${featured ? " featured" : ""}`}>{content}</article>;
  }
  return (
    <Link
      href={href}
      className={`metric-card dashboard-kpi-link${featured ? " featured" : ""}`}
      aria-label={`${label}. Abrir oportunidades filtradas.`}
    >
      {content}
    </Link>
  );
}

function SavingsValues({ totals }: { totals: MoneyTotal[] }) {
  if (!totals.length) return <>—</>;
  return (
    <span>
      {totals.map((total, index) => (
        <span key={total.currency}>
          {index ? " · " : ""}
          {formatMoney(total.amount, total.currency)}/mês
        </span>
      ))}
    </span>
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

function SeverityBreakdown({
  summary,
  state,
}: {
  summary: ExecutiveDashboardSummary | null;
  state: DashboardQueryState;
}) {
  if (!summary) return null;
  const items = [
    ["critical", "Crítica", summary.severity.critical],
    ["high", "Alta", summary.severity.high],
    ["medium", "Média", summary.severity.medium],
    ["low", "Baixa", summary.severity.low],
  ] as const;
  const total = Math.max(summary.opportunities.open, 1);
  return (
    <div className="dashboard-severity-list">
      {items.map(([severity, label, value]) => {
        const content = (
          <>
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
            {severity !== "critical" ? <ArrowRight size={15} /> : null}
          </>
        );
        if (severity === "critical") {
          return (
            <div key={severity} className="dashboard-severity-row">
              {content}
            </div>
          );
        }
        return (
          <Link
            key={severity}
            href={scopedDashboardHref("/opportunities", state, {
              current: "true",
              status: "open",
              severity,
            })}
            className="dashboard-severity-row"
          >
            {content}
          </Link>
        );
      })}
      {summary.severity.other > 0 ? (
        <p className="dashboard-note">
          {summary.severity.other} oportunidade(s) usam severidade fora do catálogo principal.
        </p>
      ) : null}
    </div>
  );
}

function ProviderDistribution({ summary }: { summary: ExecutiveDashboardSummary | null }) {
  if (!summary?.by_provider.length) return null;
  return (
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
          <span>
            <Cloud size={15} /> {providerLabel(item.provider)}
            <small><SavingsValues totals={item.savings} /></small>
          </span>
          <strong>{item.open}</strong>
        </Link>
      ))}
    </div>
  );
}

function AccountRanking({ summary }: { summary: ExecutiveDashboardSummary | null }) {
  if (!summary?.by_account.length) return null;
  return (
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
            <Building2 size={15} /> {item.account_name || item.account_id}
            <small>
              {providerLabel(item.provider)} · <SavingsValues totals={item.savings} />
            </small>
          </span>
          <strong>{item.open}</strong>
        </Link>
      ))}
    </div>
  );
}

function ServiceRuleRanking({
  summary,
  state,
}: {
  summary: ExecutiveDashboardSummary | null;
  state: DashboardQueryState;
}) {
  if (!summary) return null;
  return (
    <div className="dashboard-distributions">
      <div>
        <h3>Serviços</h3>
        <div className="dashboard-ranked-list">
          {summary.by_service.map((item) => (
            <Link
              key={item.service}
              href={scopedDashboardHref("/opportunities", state, {
                current: "true",
                status: "open",
                service: item.service,
              })}
            >
              <span>
                <Cloud size={15} /> {item.service}
                <small><SavingsValues totals={item.savings} /></small>
              </span>
              <strong>{item.open}</strong>
            </Link>
          ))}
        </div>
      </div>
      <div>
        <h3>Regras</h3>
        <div className="dashboard-ranked-list">
          {summary.by_rule.map((item) => (
            <Link
              key={item.rule_key}
              href={scopedDashboardHref("/opportunities", state, {
                current: "true",
                status: "open",
                rule: item.rule_key,
              })}
            >
              <span>
                <Wrench size={15} /> {item.rule_key}
                <small><SavingsValues totals={item.savings} /></small>
              </span>
              <strong>{item.open}</strong>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
