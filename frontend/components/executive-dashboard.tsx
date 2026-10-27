"use client";

import Link from "next/link";
import { useMemo, type CSSProperties, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  CircleDollarSign,
  Cloud,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  AccountSelector,
  ChartCard,
  CurrencyDisplay,
  DataState,
  FilterBar,
  MetricCard,
  PageHeader,
  ProviderBadge,
  ProviderSelector,
  RecommendationCard,
  Section,
  StatusIndicator,
} from "@/components/aven";
import { Alert, Button } from "@/components/ui";
import { DashboardOperationalInsights as CollectionFailureOperationalInsights } from "@/components/dashboard-operational-insights";
import { formatDate } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import {
  buildDashboardApiQuery,
  buildDashboardNewOpportunitiesHref,
  buildDashboardRecentOpportunitiesHref,
  parseDashboardSearchParams,
  patchDashboardUrl,
  scopedDashboardHref,
} from "@/lib/dashboard-query.mjs";
import type { DashboardQueryState } from "@/lib/dashboard-query.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import type { CollectionOptions, DashboardSummary } from "@/lib/types";
import styles from "./executive-dashboard.module.css";

type MoneyTotal = { currency: string; amount: string };
type NewSincePreviousDetails = {
  count: number;
  first_seen_count: number;
  reappeared_count: number;
  comparable_accounts: number;
  accounts_without_baseline: number;
  rules_version_changed: boolean;
  rules_version_unknown: boolean;
  partial_coverage: boolean;
  comparison_context: string | null;
};

type ExecutiveDashboardSummary = Omit<
  DashboardSummary,
  "opportunities" | "severity" | "by_provider" | "by_account" | "top_opportunities"
> & {
  data_updated_at: string | null;
  opportunities: DashboardSummary["opportunities"] & {
    new_since_previous_details?: NewSincePreviousDetails | null;
  };
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

const EMPTY_OPTIONS: CollectionOptions = {
  providers: [],
  accounts: [],
  has_more_accounts: false,
};

function noop() {}

export function DashboardBoot() {
  return (
    <div className={styles.page}>
      <PageHeader
        title="Visão geral"
        description="Potencial de otimização e saúde operacional do ambiente em um único lugar."
      />
      <FilterBar aria-label="Carregando filtros do Dashboard">
        <ProviderSelector
          label="Cloud"
          options={[]}
          value=""
          onChange={noop}
          loading
          clearable={false}
          searchable={false}
        />
        <AccountSelector
          label="Conta"
          options={[]}
          value=""
          onChange={noop}
          loading
          clearable={false}
          searchable={false}
        />
      </FilterBar>
      <div className={styles.metricGrid} aria-label="Carregando indicadores executivos">
        {["Oportunidades em aberto", "Economia potencial", "Novas vs coleta anterior", "Escopos válidos"].map((label) => (
          <MetricCard key={label} label={label} value={null} loading />
        ))}
      </div>
      <ChartCard title="Concentração por serviço" loading>
        <span />
      </ChartCard>
    </div>
  );
}

export function ExecutiveDashboard() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<DashboardQueryState>(() => parseDashboardSearchParams(searchKey), [searchKey]);
  const apiQuery = useMemo(() => buildDashboardApiQuery(state), [state.accountId, state.provider]);
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
  const options = optionsRequest.data ?? EMPTY_OPTIONS;
  const summaryLoading = summaryRequest.isLoading;
  const optionsLoading = optionsRequest.isLoading;
  const summaryError = summaryRequest.error?.message || "";
  const optionsError = optionsRequest.error?.message || "";

  function updateScope(patch: Record<string, string | null>) {
    const params = patchDashboardUrl(searchKey, patch);
    router.replace(`/${params.size ? `?${params.toString()}` : ""}`, { scroll: false });
  }

  const selectedAccountKey = state.provider && state.accountId ? `${state.provider}|${state.accountId}` : "";
  const selectedAccount = options.accounts.find(
    (account) => account.provider === state.provider && account.account_id === state.accountId,
  );
  const scopeDescription = state.accountId
    ? `${selectedAccount?.account_name || state.accountId} · ${providerLabel(state.provider)}`
    : state.provider
      ? `${providerLabel(state.provider)} · todas as contas`
      : "Todas as clouds · todas as contas";

  const opportunityHref = (extra: Record<string, string | number | null | undefined> = {}) =>
    scopedDashboardHref("/opportunities", state, { current: "true", ...extra });

  const totals = summary?.financial.totals || [];
  const hasBacklog = Boolean(summary?.opportunities.open);
  const newDetails = summary?.opportunities.new_since_previous_details ?? null;
  const newHref = buildDashboardNewOpportunitiesHref(state, newDetails?.comparison_context, "new_vs_previous");
  const firstSeenHref = buildDashboardNewOpportunitiesHref(state, newDetails?.comparison_context, "first_seen");
  const reappearedHref = buildDashboardNewOpportunitiesHref(state, newDetails?.comparison_context, "reappeared");
  const recentHref = buildDashboardRecentOpportunitiesHref(state);
  const newDetail = newDetails
    ? `${newDetails.first_seen_count} primeira identificação · ${newDetails.reappeared_count} reapareceram`
    : "Comparação com a última coleta válida disponível";

  const providerOptions = options.providers.map((provider) => ({
    value: provider,
    label: providerLabel(provider),
  }));
  const accountOptions = options.accounts.map((account) => ({
    value: `${account.provider}|${account.account_id}`,
    label: account.account_name || account.account_id,
    accountId: account.account_id,
    provider: providerLabel(account.provider),
  }));

  const headerMetadata = summaryLoading ? null : (
    <div className={styles.headerMetadata}>
      <StatusIndicator
        status={summary?.scope.has_current_data ? "success" : "neutral"}
        label={summary?.scope.has_current_data ? "Dados atuais disponíveis" : "Sem dados atuais"}
      />
      <span>{scopeDescription}</span>
      <span>
        {summary?.data_updated_at
          ? `Dados atualizados até ${formatDate(summary.data_updated_at)}`
          : "Sem referência de atualização para este escopo"}
      </span>
    </div>
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title="Visão geral"
        description="Potencial atual de otimização, concentração de oportunidades e saúde operacional do ambiente."
        metadata={headerMetadata}
        actions={
          <Button
            variant="secondary"
            loading={summaryRequest.isFetching || optionsRequest.isFetching}
            leadingIcon={<RefreshCw {...iconDefaults} />}
            onClick={() => {
              void summaryRequest.refetch();
              void optionsRequest.refetch();
            }}
          >
            Atualizar
          </Button>
        }
      />

      <FilterBar
        aria-label="Filtros da Visão Geral"
        clearAction={
          state.provider || state.accountId ? (
            <Button variant="ghost" size="sm" onClick={() => updateScope({ provider: null, account_id: null })}>
              Limpar escopo
            </Button>
          ) : null
        }
      >
        <ProviderSelector
          label="Cloud"
          placeholder="Todas as clouds"
          options={providerOptions}
          value={state.provider}
          loading={optionsLoading}
          onChange={(provider) => updateScope({ provider: provider || null, account_id: null })}
          clearable={false}
          searchable={false}
        />
        <AccountSelector
          label="Conta"
          placeholder="Todas as contas"
          options={accountOptions}
          value={selectedAccountKey}
          loading={optionsLoading}
          clearable={false}
          searchable={false}
          onChange={(value) => {
            if (!value) {
              updateScope({ account_id: null });
              return;
            }
            const separator = value.indexOf("|");
            updateScope({
              provider: value.slice(0, separator),
              account_id: value.slice(separator + 1),
            });
          }}
        />
      </FilterBar>

      {optionsError ? (
        <Alert variant="warning" title="Filtros parcialmente indisponíveis" description={optionsError} />
      ) : null}
      {options.has_more_accounts ? (
        <Alert
          variant="info"
          title="Lista de contas limitada"
          description="O seletor mostra as primeiras 100 contas; os indicadores continuam considerando todo o escopo selecionado."
        />
      ) : null}

      <CollectionFailureOperationalInsights />

      <DataState
        error={summaryError || undefined}
        empty={Boolean(!summaryLoading && summary && !summary.scope.has_current_data)}
        emptyTitle="Nenhum dado válido no escopo atual"
        emptyDescription="Execute uma coleta válida ou ajuste os filtros para visualizar os indicadores."
        errorFallback={
          <Alert
            variant="danger"
            title="Não foi possível carregar a Visão Geral"
            description={summaryError}
            actions={
              <Button variant="outline" size="sm" onClick={() => void summaryRequest.refetch()}>
                Tentar novamente
              </Button>
            }
          />
        }
      >
        <div className={styles.dashboardContent}>
          <Section title="Indicadores principais" description="Leitura executiva do escopo atual.">
            <div className={styles.metricGrid} aria-label="Indicadores executivos">
              <MetricCard
                loading={summaryLoading}
                icon={<Activity {...iconDefaults} />}
                label="Oportunidades em aberto"
                value={summary?.opportunities.open}
                supportingText={
                  <MetricSupport
                    text="Backlog OPEN atual e não arquivado"
                    href={opportunityHref({ status: "open" })}
                  />
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<CircleDollarSign {...iconDefaults} />}
                label="Economia potencial mensal"
                value={<SavingsValues totals={totals} />}
                supportingText={
                  <MetricSupport
                    text="Moedas permanecem separadas; nenhum câmbio é inferido"
                    href={opportunityHref({ status: "open", sort: "estimated_savings", order: "desc" })}
                  />
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<Sparkles {...iconDefaults} />}
                label="Novas vs coleta anterior"
                value={summary?.opportunities.new_since_previous}
                supportingText={<MetricSupport text={newDetail} href={newHref || undefined} />}
                status={
                  newDetails?.partial_coverage ? (
                    <StatusIndicator status="warning" label="Cobertura parcial" />
                  ) : undefined
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<ShieldCheck {...iconDefaults} />}
                label="Escopos válidos"
                value={summary?.scope.valid_scope_count}
                supportingText="Contas com uma coleta válida disponível para o resumo atual"
              />
            </div>
          </Section>

          {!summaryLoading && newDetails ? (
            <div className={styles.comparisonContext}>
              <span>{newDetails.comparable_accounts} conta(s) comparável(is)</span>
              {newDetails.accounts_without_baseline ? <span>{newDetails.accounts_without_baseline} sem baseline</span> : null}
              {firstSeenHref ? <Link href={firstSeenHref}>{newDetails.first_seen_count} primeira identificação</Link> : null}
              {reappearedHref ? <Link href={reappearedHref}>{newDetails.reappeared_count} reapareceram</Link> : null}
              <Link href={recentHref}>Identificadas nas últimas 24h</Link>
            </div>
          ) : null}

          <Section
            title="Análise do backlog"
            description="Concentração das oportunidades atuais sem converter moedas ou inventar série temporal de custos."
          >
            <div className={styles.analysisGrid}>
              <ChartCard
                title="Concentração por serviço"
                description="Quantidade de oportunidades em aberto por serviço."
                loading={summaryLoading}
                empty={Boolean(!summaryLoading && summary && summary.by_service.length === 0)}
                emptyTitle="Sem oportunidades por serviço"
                emptyDescription="Não há distribuição disponível para o escopo atual."
                actions={<TextLink href={opportunityHref({ status: "open" })}>Ver oportunidades</TextLink>}
              >
                <ServiceOpportunityChart summary={summary} state={state} />
              </ChartCard>

              <Section
                appearance="card"
                title="Estado das oportunidades"
                description="Lifecycle atual do mesmo escopo executivo."
              >
                <DataState loading={summaryLoading}>
                  <div className={styles.lifecycleList}>
                    <LifecycleItem
                      icon={<Activity {...iconDefaults} />}
                      label="Em aberto"
                      value={summary?.opportunities.open}
                      href={opportunityHref({ status: "open" })}
                      status="info"
                    />
                    <LifecycleItem
                      icon={<CheckCircle2 {...iconDefaults} />}
                      label="Tratadas"
                      value={summary?.opportunities.treated}
                      href={opportunityHref({ status: "treated" })}
                      status="success"
                    />
                    <LifecycleItem
                      icon={<XCircle {...iconDefaults} />}
                      label="Rejeitadas"
                      value={summary?.opportunities.rejected}
                      href={opportunityHref({ status: "rejected" })}
                      status="neutral"
                    />
                  </div>
                </DataState>
              </Section>
            </div>
          </Section>

          <Section
            title="Distribuição por cloud"
            description="Backlog e potencial de economia permanecem associados ao provider real."
          >
            <ProviderDistribution summary={summary} loading={summaryLoading} />
          </Section>

          <Section
            title="Maiores oportunidades"
            description="Resumo das oportunidades de maior impacto no escopo atual."
            actions={
              <TextLink href={opportunityHref({ status: "open", sort: "estimated_savings", order: "desc" })}>
                Ver todas
              </TextLink>
            }
          >
            <TopOpportunities summary={summary} loading={summaryLoading} />
          </Section>

          {!summaryLoading && summary && !hasBacklog ? (
            <Alert
              variant="success"
              title="Nenhuma oportunidade em aberto"
              description="O escopo atual não possui backlog operacional acionável."
            />
          ) : null}
        </div>
      </DataState>
    </div>
  );
}

export function DashboardOperationalInsights() {
  return <CollectionFailureOperationalInsights />;
}

function MetricSupport({ text, href }: { text: ReactNode; href?: string }) {
  return (
    <span className={styles.metricSupport}>
      <span>{text}</span>
      {href ? <Link href={href}>Abrir detalhe</Link> : null}
    </span>
  );
}

function SavingsValues({ totals }: { totals: MoneyTotal[] }) {
  if (!totals.length) return <>—</>;
  return (
    <span className={styles.moneyStack}>
      {totals.map((total) => (
        <CurrencyDisplay
          key={total.currency}
          value={Number(total.amount)}
          currency={total.currency}
          locale="pt-BR"
          currencyDisplay="code"
        />
      ))}
    </span>
  );
}

function TextLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link className={styles.textLink} href={href}>
      <span>{children}</span>
      <ArrowRight {...iconDefaults} aria-hidden="true" />
    </Link>
  );
}

function ServiceOpportunityChart({
  summary,
  state,
}: {
  summary: ExecutiveDashboardSummary | null;
  state: DashboardQueryState;
}) {
  if (!summary?.by_service.length) return null;
  const maximum = Math.max(...summary.by_service.map((item) => item.open), 1);
  return (
    <div
      className={styles.serviceChart}
      role="img"
      aria-label="Distribuição das oportunidades em aberto por serviço"
    >
      {summary.by_service.map((item) => {
        const ratio = `${(item.open / maximum) * 100}%`;
        return (
          <Link
            key={item.service}
            className={styles.chartRow}
            href={scopedDashboardHref("/opportunities", state, {
              current: "true",
              status: "open",
              service: item.service,
            })}
          >
            <div className={styles.chartRowHeader}>
              <span>{item.service}</span>
              <strong>{item.open}</strong>
            </div>
            <div className={styles.chartTrack} aria-hidden="true">
              <span
                className={styles.chartFill}
                style={{ "--dashboard-bar-value": ratio } as CSSProperties}
              />
            </div>
            <SavingsValues totals={item.savings} />
          </Link>
        );
      })}
    </div>
  );
}

function LifecycleItem({
  icon,
  label,
  value,
  href,
  status,
}: {
  icon: ReactNode;
  label: string;
  value: number | undefined;
  href: string;
  status: "neutral" | "info" | "success";
}) {
  return (
    <Link className={styles.lifecycleItem} href={href} aria-label={`${label}: ${value ?? "sem valor"}`}>
      <span className={styles.lifecycleIcon} aria-hidden="true">{icon}</span>
      <span className={styles.lifecycleCopy}>
        <span>{label}</span>
        <strong>{value ?? "—"}</strong>
      </span>
      <StatusIndicator status={status} label="Ver detalhe" />
    </Link>
  );
}

function ProviderDistribution({
  summary,
  loading,
}: {
  summary: ExecutiveDashboardSummary | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className={styles.providerGrid}>
        <MetricCard label="Cloud" value={null} loading />
        <MetricCard label="Cloud" value={null} loading />
      </div>
    );
  }
  if (!summary?.by_provider.length) {
    return <Alert variant="info" title="Sem distribuição por cloud" description="Não há backlog aberto para distribuir no escopo atual." />;
  }
  return (
    <div className={styles.providerGrid}>
      {summary.by_provider.map((item) => (
        <MetricCard
          key={item.provider}
          icon={<Cloud {...iconDefaults} />}
          label={<ProviderBadge provider={item.provider} />}
          value={item.open}
          supportingText={
            <MetricSupport
              text={<SavingsValues totals={item.savings} />}
              href={scopedDashboardHref(
                "/opportunities",
                { provider: item.provider, accountId: "" },
                { current: "true", status: "open" },
              )}
            />
          }
        />
      ))}
    </div>
  );
}

function TopOpportunities({
  summary,
  loading,
}: {
  summary: ExecutiveDashboardSummary | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <DataState loading>
        <span />
      </DataState>
    );
  }
  if (!summary?.top_opportunities.length) {
    return <Alert variant="success" title="Sem oportunidades abertas" description="Nenhuma oportunidade de maior impacto está disponível no escopo atual." />;
  }
  return (
    <div className={styles.opportunityGrid}>
      {summary.top_opportunities.slice(0, 4).map((item) => {
        const href = scopedDashboardHref(
          "/opportunities",
          { provider: item.provider, accountId: item.account_id },
          { current: "true", status: "open", opportunity_id: item.id },
        );
        return (
          <RecommendationCard
            key={item.id}
            title={item.title}
            description={`${item.service || item.rule_key} · ${item.resource_name || item.resource_id}`}
            provider={item.provider}
            status={severityStatus(item.severity)}
            statusLabel={severityLabel(item.severity)}
            metadata={
              <div className={styles.opportunityMetadata}>
                <span>{item.account_name || item.account_id}{item.region ? ` · ${item.region}` : ""}</span>
                <span className={styles.opportunitySavings}>
                  <CurrencyDisplay
                    value={Number(item.estimated_monthly_savings)}
                    currency={item.currency}
                    locale="pt-BR"
                    currencyDisplay="code"
                  />
                  <span>/mês</span>
                </span>
              </div>
            }
            actions={<TextLink href={href}>Abrir oportunidade</TextLink>}
          />
        );
      })}
    </div>
  );
}

function severityStatus(severity: string): "neutral" | "info" | "warning" | "danger" {
  switch (severity.toLowerCase()) {
    case "critical":
    case "high":
      return "danger";
    case "medium":
      return "warning";
    case "low":
      return "info";
    default:
      return "neutral";
  }
}

function severityLabel(severity: string) {
  switch (severity.toLowerCase()) {
    case "critical":
      return "Crítica";
    case "high":
      return "Alta";
    case "medium":
      return "Média";
    case "low":
      return "Baixa";
    default:
      return severity;
  }
}
