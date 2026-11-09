"use client";

import Link from "next/link";
import { useFormatter, useTranslations } from "next-intl";
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
  ResourceIdentifier,
  Section,
  StatusIndicator,
} from "@/components/aven";
import { Alert, Button } from "@/components/ui";
import { DashboardOperationalInsights as CollectionFailureOperationalInsights } from "@/components/dashboard-operational-insights";
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
  const t = useTranslations("dashboard");
  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("boot.description")}
      />
      <FilterBar aria-label={t("boot.loadingFilters")}>
        <ProviderSelector
          label={t("filters.cloud")}
          options={[]}
          value=""
          onChange={noop}
          loading
          clearable={false}
          searchable={false}
        />
        <AccountSelector
          label={t("filters.account")}
          options={[]}
          value=""
          onChange={noop}
          loading
          clearable={false}
          searchable={false}
        />
      </FilterBar>
      <div className={styles.metricGrid} aria-label={t("boot.loadingMetrics")}>
        {[t("metrics.openOpportunities"), t("metrics.potentialSavings"), t("metrics.newSincePrevious"), t("metrics.validScopes")].map((label) => (
          <MetricCard key={label} label={label} value={null} loading />
        ))}
      </div>
      <ChartCard title={t("charts.serviceConcentration")} loading>
        <span />
      </ChartCard>
    </div>
  );
}

export function ExecutiveDashboard() {
  const t = useTranslations("dashboard");
  const format = useFormatter();
  const router = useRouter();
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo<DashboardQueryState>(() => parseDashboardSearchParams(searchKey), [searchKey]);
  const apiQuery = useMemo(() => buildDashboardApiQuery(state), [state]);
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
      ? t("scope.withProvider", { provider: providerLabel(state.provider) })
      : t("scope.allCloudsAccounts");

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
    ? t("comparison.newDetail", { first: newDetails.first_seen_count, reappeared: newDetails.reappeared_count })
    : t("comparison.previousAvailable");

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
        label={summary?.scope.has_current_data ? t("status.currentData") : t("status.noCurrentData")}
      />
      <span>{scopeDescription}</span>
      <span>
        {summary?.data_updated_at
          ? t("status.updatedUntil", { date: format.dateTime(new Date(summary.data_updated_at), { dateStyle: "short", timeStyle: "short" }) })
          : t("status.noUpdateReference")}
      </span>
    </div>
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
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
            {t("actions.refresh")}
          </Button>
        }
      />

      <FilterBar
        aria-label={t("filters.aria")}
        clearAction={
          state.provider || state.accountId ? (
            <Button variant="ghost" size="sm" onClick={() => updateScope({ provider: null, account_id: null })}>
              {t("filters.clearScope")}
            </Button>
          ) : null
        }
      >
        <ProviderSelector
          label={t("filters.cloud")}
          placeholder={t("filters.allClouds")}
          options={providerOptions}
          value={state.provider}
          loading={optionsLoading}
          onChange={(provider) => updateScope({ provider: provider || null, account_id: null })}
          clearable={false}
          searchable={false}
        />
        <AccountSelector
          label={t("filters.account")}
          placeholder={t("filters.allAccounts")}
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
        <Alert variant="warning" title={t("errors.partialFilters")} description={optionsError} />
      ) : null}
      {options.has_more_accounts ? (
        <Alert
          variant="info"
          title={t("warnings.limitedAccounts")}
          description={t("warnings.limitedAccountsDetail")}
        />
      ) : null}

      <DataState
        error={summaryError || undefined}
        empty={Boolean(!summaryLoading && summary && !summary.scope.has_current_data)}
        emptyTitle={t("empty.noValidScope")}
        emptyDescription={t("empty.runCollection")}
        errorFallback={
          <Alert
            variant="danger"
            title={t("errors.loadOverview")}
            description={summaryError}
            actions={
              <Button variant="outline" size="sm" onClick={() => void summaryRequest.refetch()}>
                {t("actions.retry")}
              </Button>
            }
          />
        }
      >
        <div className={styles.dashboardContent}>
          <Section title={t("sections.primaryIndicators")} description={t("sections.primaryDescription")}>
            <div className={styles.metricGrid} aria-label={t("metrics.aria")}>
              <MetricCard
                loading={summaryLoading}
                icon={<Activity {...iconDefaults} />}
                label={t("metrics.openOpportunities")}
                value={summary?.opportunities.open}
                supportingText={
                  <MetricSupport
                    text={t("metrics.openBacklogHelp")}
                    href={opportunityHref({ status: "open" })}
                  />
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<CircleDollarSign {...iconDefaults} />}
                label={t("metrics.monthlySavings")}
                value={<SavingsValues totals={totals} />}
                supportingText={
                  <MetricSupport
                    text={t("metrics.currenciesSeparate")}
                    href={opportunityHref({ status: "open", sort: "estimated_savings", order: "desc" })}
                  />
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<Sparkles {...iconDefaults} />}
                label={t("metrics.newSincePrevious")}
                value={summary?.opportunities.new_since_previous}
                supportingText={<MetricSupport text={newDetail} href={newHref || undefined} />}
                status={
                  newDetails?.partial_coverage ? (
                    <StatusIndicator status="warning" label={t("status.partialCoverage")} />
                  ) : undefined
                }
              />
              <MetricCard
                loading={summaryLoading}
                icon={<ShieldCheck {...iconDefaults} />}
                label={t("metrics.validScopes")}
                value={summary?.scope.valid_scope_count}
                supportingText={t("metrics.validScopeHelp")}
              />
            </div>
          </Section>

          {!summaryLoading && newDetails ? (
            <div className={styles.comparisonContext}>
              <span>{t("comparison.comparable", { count: newDetails.comparable_accounts })}</span>
              {newDetails.accounts_without_baseline ? <span>{t("comparison.withoutBaseline", { count: newDetails.accounts_without_baseline })}</span> : null}
              {firstSeenHref ? <Link href={firstSeenHref}>{t("comparison.firstIdentifications", { count: newDetails.first_seen_count })}</Link> : null}
              {reappearedHref ? <Link href={reappearedHref}>{t("comparison.reappeared", { count: newDetails.reappeared_count })}</Link> : null}
              <Link href={recentHref}>{t("comparison.last24Hours")}</Link>
            </div>
          ) : null}

          <Section
            title={t("sections.backlog")}
            description={t("sections.backlogDescription")}
          >
            <div className={styles.analysisGrid}>
              <ChartCard
                title={t("charts.serviceConcentration")}
                description={t("charts.serviceDescription")}
                loading={summaryLoading}
                empty={Boolean(!summaryLoading && summary && summary.by_service.length === 0)}
                emptyTitle={t("empty.noServiceOpportunities")}
                emptyDescription={t("empty.noServiceDistribution")}
                actions={<TextLink href={opportunityHref({ status: "open" })}>{t("actions.viewOpportunities")}</TextLink>}
              >
                <ServiceOpportunityChart summary={summary} state={state} />
              </ChartCard>

              <Section
                appearance="card"
                title={t("sections.lifecycle")}
                description={t("sections.lifecycleDescription")}
              >
                <DataState loading={summaryLoading}>
                  <div className={styles.lifecycleList}>
                    <LifecycleItem
                      icon={<Activity {...iconDefaults} />}
                      label={t("status.open")}
                      value={summary?.opportunities.open}
                      href={opportunityHref({ status: "open" })}
                      status="info"
                    />
                    <LifecycleItem
                      icon={<CheckCircle2 {...iconDefaults} />}
                      label={t("status.treated")}
                      value={summary?.opportunities.treated}
                      href={opportunityHref({ status: "treated" })}
                      status="success"
                    />
                    <LifecycleItem
                      icon={<XCircle {...iconDefaults} />}
                      label={t("status.rejected")}
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
            title={t("sections.cloudDistribution")}
            description={t("sections.cloudDescription")}
          >
            <ProviderDistribution summary={summary} loading={summaryLoading} />
          </Section>

          <Section
            title={t("sections.topOpportunities")}
            description={t("sections.topDescription")}
            actions={
              <TextLink href={opportunityHref({ status: "open", sort: "estimated_savings", order: "desc" })}>
                {t("actions.viewAll")}
              </TextLink>
            }
          >
            <TopOpportunities summary={summary} loading={summaryLoading} />
          </Section>

          {!summaryLoading && summary && !hasBacklog ? (
            <Alert
              variant="success"
              title={t("empty.noOpenOpportunities")}
              description={t("empty.noActionableBacklog")}
            />
          ) : null}
        </div>
      </DataState>

      <CollectionFailureOperationalInsights />
    </div>
  );
}

export function DashboardOperationalInsights() {
  return <CollectionFailureOperationalInsights />;
}

function MetricSupport({ text, href }: { text: ReactNode; href?: string }) {
  const t = useTranslations("dashboard");
  return (
    <span className={styles.metricSupport}>
      <span>{text}</span>
      {href ? <Link href={href}>{t("actions.openDetail")}</Link> : null}
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
  const t = useTranslations("dashboard");
  if (!summary?.by_service.length) return null;
  const maximum = Math.max(...summary.by_service.map((item) => item.open), 1);
  return (
    <div
      className={styles.serviceChart}
      role="group"
      aria-label={t("charts.serviceAria")}
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
  const t = useTranslations("dashboard");
  return (
    <Link className={styles.lifecycleItem} href={href} aria-label={`${label}: ${value ?? t("empty.noValue")}`}>
      <span className={styles.lifecycleIcon} aria-hidden="true">{icon}</span>
      <span className={styles.lifecycleCopy}>
        <span>{label}</span>
        <strong>{value ?? "—"}</strong>
      </span>
      <StatusIndicator status={status} label={t("actions.viewDetail")} />
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
  const t = useTranslations("dashboard");
  if (loading) {
    return (
      <div className={styles.providerGrid}>
        <MetricCard label={t("filters.cloud")} value={null} loading />
        <MetricCard label={t("filters.cloud")} value={null} loading />
      </div>
    );
  }
  if (!summary?.by_provider.length) {
    return <Alert variant="info" title={t("empty.noCloudDistribution")} description={t("empty.noOpenBacklogDistribution")} />;
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
  const t = useTranslations("dashboard");
  if (loading) {
    return (
      <DataState loading>
        <span />
      </DataState>
    );
  }
  if (!summary?.top_opportunities.length) {
    return <Alert variant="success" title={t("empty.noOpenOpportunitiesShort")} description={t("empty.noTopOpportunities")} />;
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
            description={item.service || item.rule_key}
            resource={
              <ResourceIdentifier
                primary={item.resource_name || t("empty.unnamedResource")}
                technicalId={item.resource_name ? undefined : item.resource_id}
                copyable={false}
              />
            }
            provider={item.provider}
            status={severityStatus(item.severity)}
            statusLabel={severityLabel(item.severity, { critical: t("severity.critical"), high: t("severity.high"), medium: t("severity.medium"), low: t("severity.low") })}
            metadata={
              <div className={styles.opportunityMetadata}>
                <span>{item.account_name || item.account_id}{item.region ? ` · ${item.region}` : ""}</span>
                <span className={styles.opportunitySavings}>
                  <CurrencyDisplay
                    value={Number(item.estimated_monthly_savings)}
                    currency={item.currency}
                                        currencyDisplay="code"
                  />
                  <span>{t("metrics.monthSuffix")}</span>
                </span>
              </div>
            }
            actions={<TextLink href={href}>{t("actions.openOpportunity")}</TextLink>}
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

function severityLabel(severity: string, labels: Record<"critical" | "high" | "medium" | "low", string>) {
  switch (severity.toLowerCase()) {
    case "critical":
      return labels.critical;
    case "high":
      return labels.high;
    case "medium":
      return labels.medium;
    case "low":
      return labels.low;
    default:
      return severity;
  }
}
