"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, RotateCcw, Settings2 } from "lucide-react";
import {
  AccountSelector,
  ChartCard,
  CurrencyDisplay,
  DataState,
  DateRangePicker,
  FilterBar,
  MetricCard,
  PageHeader,
  PercentageDisplay,
  ProviderBadge,
  Section,
  StatusIndicator,
  type DateRangeValue,
  type ProductStatus,
} from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  EmptyState,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import { ApiError, api } from "@/lib/api";
import {
  getAwsBillingBreakdown,
  getAwsBillingSummary,
  getAwsBillingTimeSeries,
  listBillingProfiles,
} from "@/lib/billing";
import type {
  AwsBillingRequest,
  BillingBreakdownItem,
  BillingBreakdownResponse,
  BillingDataStatus,
  BillingGranularity,
  BillingGroupBy,
  BillingMetric,
  BillingProfile,
  BillingSummaryResponse,
  BillingTimeSeriesResponse,
} from "@/lib/billing";
import {
  BILLING_PERIOD_PRESETS,
  billingQuerySignature,
  billingStatusLabel,
  billingVariation,
  formatBillingRange,
  groupBillingByCurrency,
  hasBillingAccountSelection,
  inclusiveEndDate,
  mapBillingTimeSeriesToChartData,
  parseBillingAccountIds,
  previousEquivalentPeriod,
  resolveBillingPeriod,
  sameStringSet,
  topBillingItems,
} from "@/lib/billing-dashboard.mjs";
import type { BillingPeriod, BillingPeriodPreset } from "@/lib/billing-dashboard.mjs";
import type { CloudAccount } from "@/lib/types";
import { BillingCostChart } from "./billing-cost-chart";
import styles from "./billing.module.css";

const METRIC_LABELS: Record<BillingMetric, string> = {
  AMORTIZED_COST: "Custo amortizado",
  NET_AMORTIZED_COST: "Custo amortizado líquido",
  UNBLENDED_COST: "Custo não combinado",
};

const GRANULARITY_LABELS: Record<BillingGranularity, string> = {
  DAILY: "Diária",
  MONTHLY: "Mensal",
};

const GROUP_BY_LABELS: Record<BillingGroupBy, string> = {
  NONE: "Sem agrupamento",
  SERVICE: "Serviço",
  ACCOUNT: "Conta",
};

const AWS_RECORD_TYPES = [
  "Credit",
  "DiscountedUsage",
  "Fee",
  "Refund",
  "RIFee",
  "SavingsPlanCoveredUsage",
  "SavingsPlanNegation",
  "SavingsPlanRecurringFee",
  "SavingsPlanUpfrontFee",
  "Tax",
  "Usage",
] as const;

const VALID_PRESETS = new Set(BILLING_PERIOD_PRESETS.map((item) => item.value));
const VALID_METRICS = new Set<BillingMetric>(Object.keys(METRIC_LABELS) as BillingMetric[]);
const VALID_GRANULARITIES = new Set<BillingGranularity>(Object.keys(GRANULARITY_LABELS) as BillingGranularity[]);
const VALID_GROUPINGS = new Set<BillingGroupBy>(Object.keys(GROUP_BY_LABELS) as BillingGroupBy[]);
const VALID_RECORD_TYPES = new Set<string>(AWS_RECORD_TYPES);

type CurrentUser = { role: string };
type SectionState<T> = { data: T | null; loading: boolean; error: string };

function sectionState<T>(): SectionState<T> {
  return { data: null, loading: false, error: "" };
}

function localTodayKey() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function profileSummary(profile: BillingProfile) {
  const excluded = profile.exclude_record_types.length
    ? `Exclui ${profile.exclude_record_types.join(", ")}`
    : "Sem exclusões por tipo";
  return `${GRANULARITY_LABELS[profile.granularity]} · ${METRIC_LABELS[profile.metric]} · ${GROUP_BY_LABELS[profile.group_by]} · ${excluded}`;
}

function billingErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "ACCESS_DENIED":
        return "As credenciais configuradas não possuem permissão para consultar Billing neste escopo.";
      case "COST_EXPLORER_UNAVAILABLE":
        return "O AWS Cost Explorer não está disponível para este escopo. Verifique a habilitação e as preferências de acesso da conta.";
      case "INVALID_BILLING_SCOPE":
        return "As contas selecionadas não puderam ser consultadas em um billing scope válido. Nenhum total parcial foi apresentado.";
      case "THROTTLED":
        return "A AWS limitou temporariamente as consultas de Billing. Tente atualizar novamente mais tarde.";
      case "ACCOUNT_NOT_FOUND":
      case "ACCOUNT_NOT_AWS":
        return "Uma das contas selecionadas não está disponível para Billing AWS.";
      case "INVALID_PERIOD":
        return "O período selecionado não é válido para uma consulta histórica do Cost Explorer.";
      case "UPSTREAM_DATA_INVALID":
        return "O Cost Explorer retornou dados que não puderam ser interpretados com segurança.";
      case "UPSTREAM_ERROR":
        return "A AWS não respondeu à consulta de Billing como esperado. Tente novamente.";
      default:
        return error.message || fallback;
    }
  }
  return error instanceof Error ? error.message : fallback;
}

function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function buildRequest(
  profile: BillingProfile,
  accountIds: number[],
  period: BillingPeriod,
  granularity: BillingGranularity,
  metric: BillingMetric,
  groupBy: BillingGroupBy,
  excludeRecordTypes: string[],
): AwsBillingRequest {
  const request: AwsBillingRequest = {
    account_ids: accountIds,
    start_date: period.start_date,
    end_date: period.end_date,
    profile_id: profile.id,
  };
  if (granularity !== profile.granularity) request.granularity = granularity;
  if (metric !== profile.metric) request.metric = metric;
  if (groupBy !== profile.group_by) request.group_by = groupBy;
  if (!sameStringSet(excludeRecordTypes, profile.exclude_record_types)) {
    request.exclude_record_types = excludeRecordTypes;
  }
  return request;
}

function statusSemantic(status: BillingDataStatus): ProductStatus {
  switch (status) {
    case "ACTUAL":
      return "success";
    case "FORECAST":
    case "INCLUDES_FORECAST":
      return "info";
    case "ESTIMATED":
    case "PARTIALLY_ESTIMATED":
    default:
      return "warning";
  }
}

function numericAmount(value: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function variationTrend(current: string, previous: string) {
  const variation = billingVariation(current, previous);
  if (variation.kind !== "percent" || variation.percent === null) return null;
  const direction = variation.percent > 0 ? "up" : variation.percent < 0 ? "down" : "flat";
  const sentiment = variation.percent > 0 ? "negative" : variation.percent < 0 ? "positive" : "neutral";
  return {
    value: variation.percent,
    direction,
    sentiment,
    label: "Variação vs período anterior",
    locale: "pt-BR",
  } as const;
}

function variationSupportingText(current: string, previous: string) {
  const variation = billingVariation(current, previous);
  if (variation.kind === "new") return "Novo custo em relação ao período anterior.";
  if (variation.kind === "unavailable") return "Variação não aplicável para esta comparação.";
  return null;
}

function BreakdownTable({
  items,
  kind,
}: {
  items: BillingBreakdownItem[];
  kind: "service" | "account";
}) {
  const groups = groupBillingByCurrency(items);
  return (
    <div className={styles.breakdownGroups}>
      {groups.map(([currency, currencyItems]) => {
        const topItems = topBillingItems(currencyItems, 10);
        const absoluteTotal = currencyItems.reduce((sum, item) => sum + Math.abs(Number(item.amount) || 0), 0);
        return (
          <div key={currency} className={styles.breakdownGroup}>
            <div className={styles.currencyHeading}>
              <strong>{currency}</strong>
              <span>Top {Math.min(10, currencyItems.length)} de {currencyItems.length}</span>
            </div>
            <Table>
              <TableHeader>
                <TableRow staticRow>
                  <TableHead>{kind === "service" ? "Serviço" : "Conta"}</TableHead>
                  {kind === "account" && <TableHead>AWS Account ID</TableHead>}
                  <TableHead numeric>Participação</TableHead>
                  <TableHead numeric>Valor</TableHead>
                  <TableHead>Estado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topItems.map((item) => {
                  const amount = numericAmount(item.amount);
                  const share = amount === null || absoluteTotal === 0
                    ? null
                    : (Math.abs(amount) / absoluteTotal) * 100;
                  return (
                    <TableRow key={`${currency}-${item.key}`}>
                      <TableCell>
                        <strong>{kind === "account" ? (item.display_name || item.label || item.key) : (item.label || item.key)}</strong>
                      </TableCell>
                      {kind === "account" && (
                        <TableCell>
                          <code className={styles.accountId}>{item.aws_account_id || item.key}</code>
                        </TableCell>
                      )}
                      <TableCell numeric>
                        <PercentageDisplay value={share} locale="pt-BR" maximumFractionDigits={1} />
                      </TableCell>
                      <TableCell numeric>
                        <CurrencyDisplay
                          value={amount}
                          currency={item.currency}
                          locale="pt-BR"
                          currencyDisplay="code"
                          minimumFractionDigits={2}
                          maximumFractionDigits={2}
                        />
                      </TableCell>
                      <TableCell>
                        <StatusIndicator
                          status={statusSemantic(item.status)}
                          label={billingStatusLabel(item.status)}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        );
      })}
    </div>
  );
}

export default function BillingPage() {
  const [profiles, setProfiles] = useState<BillingProfile[]>([]);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [role, setRole] = useState("");
  const [initialized, setInitialized] = useState(false);
  const [bootstrapError, setBootstrapError] = useState("");

  const [profileId, setProfileId] = useState("");
  const [selectedAccountIds, setSelectedAccountIds] = useState<number[]>([]);
  const [periodPreset, setPeriodPreset] = useState<BillingPeriodPreset>("this_month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [metric, setMetric] = useState<BillingMetric>("AMORTIZED_COST");
  const [granularity, setGranularity] = useState<BillingGranularity>("DAILY");
  const [groupBy, setGroupBy] = useState<BillingGroupBy>("NONE");
  const [excludeRecordTypes, setExcludeRecordTypes] = useState<string[]>(["Credit"]);
  const [refreshRevision, setRefreshRevision] = useState(0);

  const [summary, setSummary] = useState<SectionState<BillingSummaryResponse>>(sectionState);
  const [previousSummary, setPreviousSummary] = useState<SectionState<BillingSummaryResponse>>(sectionState);
  const [timeseries, setTimeseries] = useState<SectionState<BillingTimeSeriesResponse>>(sectionState);
  const [serviceBreakdown, setServiceBreakdown] = useState<SectionState<BillingBreakdownResponse>>(sectionState);
  const [accountBreakdown, setAccountBreakdown] = useState<SectionState<BillingBreakdownResponse>>(sectionState);
  const requestSequence = useRef(0);

  const selectedProfile = useMemo(
    () => profiles.find((profile) => profile.id === profileId) || null,
    [profileId, profiles],
  );
  const period = useMemo(
    () => resolveBillingPeriod(periodPreset, { customFrom, customTo }),
    [customFrom, customTo, periodPreset],
  );
  const previousPeriod = useMemo(
    () => (period ? previousEquivalentPeriod(period, periodPreset) : null),
    [period, periodPreset],
  );
  const hasAccountSelection = hasBillingAccountSelection(selectedAccountIds);
  const hasOverrides = Boolean(
    selectedProfile
    && (
      selectedProfile.metric !== metric
      || selectedProfile.granularity !== granularity
      || selectedProfile.group_by !== groupBy
      || !sameStringSet(selectedProfile.exclude_record_types, excludeRecordTypes)
    )
  );

  const querySignature = useMemo(
    () => billingQuerySignature({
      profileId,
      accountIds: selectedAccountIds,
      period,
      metric,
      granularity,
      groupBy,
      excludeRecordTypes,
      revision: refreshRevision,
    }),
    [excludeRecordTypes, granularity, groupBy, metric, period, profileId, refreshRevision, selectedAccountIds],
  );

  const chartDatasets = useMemo(
    () => timeseries.data
      ? mapBillingTimeSeriesToChartData(timeseries.data.points, timeseries.data.group_by)
      : [],
    [timeseries.data],
  );

  const accountOptions = useMemo(
    () => accounts.map((account) => ({
      value: String(account.id),
      label: account.name || "Conta AWS",
      accountId: account.native_account_id || undefined,
      provider: account.provider,
      searchTerms: [account.native_account_id || "", account.name || ""],
    })),
    [accounts],
  );

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      listBillingProfiles(controller.signal),
      api<CloudAccount[]>("/cloud-accounts", { signal: controller.signal }),
      api<CurrentUser>("/auth/me", { signal: controller.signal }),
    ])
      .then(([profileItems, accountItems, user]) => {
        const enabledProfiles = profileItems.filter((profile) => profile.enabled);
        const awsAccounts = accountItems.filter((account) => account.provider === "aws");
        if (!enabledProfiles.length) {
          setBootstrapError("Nenhum Billing Profile habilitado está disponível.");
          return;
        }

        const params = new URLSearchParams(window.location.search);
        const requestedProfileId = params.get("profile");
        const initialProfile = enabledProfiles.find((profile) => profile.id === requestedProfileId)
          || enabledProfiles.find((profile) => profile.is_default)
          || enabledProfiles.find((profile) => profile.name === "FinOps")
          || enabledProfiles[0];

        const initialAccounts = parseBillingAccountIds(
          params.get("accounts"),
          awsAccounts.map((account) => account.id),
        );

        const requestedPreset = params.get("period") as BillingPeriodPreset | null;
        const initialPreset = requestedPreset && VALID_PRESETS.has(requestedPreset)
          ? requestedPreset
          : "this_month";
        const requestedMetric = params.get("metric") as BillingMetric | null;
        const requestedGranularity = params.get("granularity") as BillingGranularity | null;
        const requestedGroupBy = params.get("group") as BillingGroupBy | null;
        const hasExcludeOverride = params.has("exclude");
        const requestedExclusions = (params.get("exclude") || "")
          .split(",")
          .filter((value) => VALID_RECORD_TYPES.has(value));

        setProfiles(enabledProfiles);
        setAccounts(awsAccounts);
        setRole(user.role);
        setProfileId(initialProfile.id);
        setSelectedAccountIds(initialAccounts);
        setPeriodPreset(initialPreset);
        setCustomFrom(params.get("from") || "");
        setCustomTo(params.get("to") || "");
        setMetric(requestedMetric && VALID_METRICS.has(requestedMetric) ? requestedMetric : initialProfile.metric);
        setGranularity(
          requestedGranularity && VALID_GRANULARITIES.has(requestedGranularity)
            ? requestedGranularity
            : initialProfile.granularity,
        );
        setGroupBy(
          requestedGroupBy && VALID_GROUPINGS.has(requestedGroupBy)
            ? requestedGroupBy
            : initialProfile.group_by,
        );
        setExcludeRecordTypes(hasExcludeOverride ? requestedExclusions : initialProfile.exclude_record_types);
        setBootstrapError("");
      })
      .catch((error) => {
        if (!controller.signal.aborted && !isAbort(error)) {
          setBootstrapError(billingErrorMessage(error, "Falha ao preparar a área de Billing."));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setInitialized(true);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!initialized || !selectedProfile) return;
    const params = new URLSearchParams();
    params.set("profile", selectedProfile.id);
    params.set("period", periodPreset);
    if (hasAccountSelection) params.set("accounts", selectedAccountIds.join(","));
    if (periodPreset === "custom") {
      if (customFrom) params.set("from", customFrom);
      if (customTo) params.set("to", customTo);
    }
    if (metric !== selectedProfile.metric) params.set("metric", metric);
    if (granularity !== selectedProfile.granularity) params.set("granularity", granularity);
    if (groupBy !== selectedProfile.group_by) params.set("group", groupBy);
    if (!sameStringSet(excludeRecordTypes, selectedProfile.exclude_record_types)) {
      params.set("exclude", excludeRecordTypes.join(","));
    }
    const next = `/billing?${params.toString()}`;
    window.history.replaceState(window.history.state, "", next);
  }, [
    customFrom,
    customTo,
    excludeRecordTypes,
    granularity,
    groupBy,
    hasAccountSelection,
    initialized,
    metric,
    periodPreset,
    selectedAccountIds,
    selectedProfile,
  ]);

  useEffect(() => {
    if (
      !initialized
      || !selectedProfile
      || !period
      || !previousPeriod
      || !hasBillingAccountSelection(selectedAccountIds)
    ) {
      setSummary(sectionState());
      setPreviousSummary(sectionState());
      setTimeseries(sectionState());
      setServiceBreakdown(sectionState());
      setAccountBreakdown(sectionState());
      return;
    }

    const sequence = ++requestSequence.current;
    const controller = new AbortController();
    const currentRequest = buildRequest(
      selectedProfile,
      selectedAccountIds,
      period,
      granularity,
      metric,
      groupBy,
      excludeRecordTypes,
    );
    const comparisonRequest = buildRequest(
      selectedProfile,
      selectedAccountIds,
      previousPeriod,
      granularity,
      metric,
      groupBy,
      excludeRecordTypes,
    );
    const active = () => requestSequence.current === sequence && !controller.signal.aborted;

    setSummary({ data: null, loading: true, error: "" });
    setPreviousSummary({ data: null, loading: true, error: "" });
    setTimeseries({ data: null, loading: true, error: "" });
    setServiceBreakdown({ data: null, loading: true, error: "" });
    setAccountBreakdown(
      selectedAccountIds.length > 1
        ? { data: null, loading: true, error: "" }
        : sectionState(),
    );

    getAwsBillingSummary(currentRequest, controller.signal)
      .then((data) => { if (active()) setSummary({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setSummary({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo do período.") });
        }
      });

    getAwsBillingSummary(comparisonRequest, controller.signal)
      .then((data) => { if (active()) setPreviousSummary({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setPreviousSummary({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o período anterior.") });
        }
      });

    getAwsBillingTimeSeries(currentRequest, controller.signal)
      .then((data) => { if (active()) setTimeseries({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setTimeseries({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar a evolução de custos.") });
        }
      });

    getAwsBillingBreakdown({ ...currentRequest, group_by: "SERVICE" }, controller.signal)
      .then((data) => { if (active()) setServiceBreakdown({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setServiceBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo por serviço.") });
        }
      });

    if (selectedAccountIds.length > 1) {
      getAwsBillingBreakdown({ ...currentRequest, group_by: "ACCOUNT" }, controller.signal)
        .then((data) => { if (active()) setAccountBreakdown({ data, loading: false, error: "" }); })
        .catch((error) => {
          if (active() && !isAbort(error)) {
            setAccountBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo por conta.") });
          }
        });
    }

    return () => controller.abort();
  }, [initialized, querySignature]);

  function chooseProfile(nextProfileId: string) {
    const profile = profiles.find((item) => item.id === nextProfileId);
    if (!profile) return;
    setProfileId(profile.id);
    setMetric(profile.metric);
    setGranularity(profile.granularity);
    setGroupBy(profile.group_by);
    setExcludeRecordTypes(profile.exclude_record_types);
  }

  function restoreProfile() {
    if (!selectedProfile) return;
    setMetric(selectedProfile.metric);
    setGranularity(selectedProfile.granularity);
    setGroupBy(selectedProfile.group_by);
    setExcludeRecordTypes(selectedProfile.exclude_record_types);
  }

  function toggleRecordType(recordType: string, checked: boolean) {
    setExcludeRecordTypes((current) => {
      if (checked) return Array.from(new Set([...current, recordType])).sort();
      return current.filter((value) => value !== recordType);
    });
  }

  function setAccountValues(values: string[]) {
    const allowed = new Set(accounts.map((account) => account.id));
    const next = values
      .map((value) => Number(value))
      .filter((value) => Number.isInteger(value) && allowed.has(value))
      .sort((left, right) => left - right);
    setSelectedAccountIds(Array.from(new Set(next)));
  }

  function setDateRange(value: DateRangeValue) {
    setPeriodPreset("custom");
    setCustomFrom(value.startDate || "");
    setCustomTo(value.endDate || "");
  }

  const queryMetadata = hasAccountSelection && selectedProfile && period
    ? `${selectedAccountIds.length} ${selectedAccountIds.length === 1 ? "conta" : "contas"} · ${formatBillingRange(period)} · ${GRANULARITY_LABELS[granularity]} · ${GROUP_BY_LABELS[groupBy]} · ${METRIC_LABELS[metric]} · ${excludeRecordTypes.length ? `Exclui ${excludeRecordTypes.join(", ")}` : "Sem exclusões"}`
    : "";
  const anyLoading = summary.loading || previousSummary.loading || timeseries.loading || serviceBreakdown.loading || accountBreakdown.loading;
  const today = localTodayKey();
  const dateRangeValue: DateRangeValue = periodPreset === "custom"
    ? { startDate: customFrom || null, endDate: customTo || null }
    : {
        startDate: period?.start_date || null,
        endDate: period ? inclusiveEndDate(period.end_date) : null,
      };

  return (
    <div className={styles.page}>
      <PageHeader
        title="Uso e custos"
        description="Analise custos do AWS Cost Explorer por conta, período, serviço e metodologia."
        metadata={(
          <div className={styles.headerMetadata}>
            <ProviderBadge provider="aws" />
            <span>
              {selectedAccountIds.length === 0
                ? "Nenhuma conta selecionada"
                : `${selectedAccountIds.length} ${selectedAccountIds.length === 1 ? "conta selecionada" : "contas selecionadas"}`}
            </span>
          </div>
        )}
        actions={(
          <>
            {role === "admin" && (
              <Link className={styles.actionLink} href="/settings/billing/profiles">
                <Settings2 {...iconDefaults} aria-hidden="true" />
                <span>Gerenciar perfis</span>
              </Link>
            )}
            <Button
              variant="outline"
              size="sm"
              leadingIcon={<RefreshCw {...iconDefaults} />}
              disabled={!initialized || !hasAccountSelection || !period || anyLoading}
              loading={anyLoading && hasAccountSelection}
              onClick={() => setRefreshRevision((value) => value + 1)}
            >
              Atualizar
            </Button>
          </>
        )}
      />

      {bootstrapError && (
        <Alert variant="danger" title="Não foi possível preparar o Billing" description={bootstrapError} />
      )}

      <Section
        title="Contas"
        description="Selecione explicitamente uma ou mais contas. Sem seleção, nenhuma consulta de custo é executada."
      >
        <div className={styles.accountContext}>
          <AccountSelector
            label="Contas AWS"
            options={accountOptions}
            multiple
            value={selectedAccountIds.map(String)}
            onChange={setAccountValues}
            selectAll
            selectAllLabel="Selecionar todas"
            clearLabel="Limpar seleção"
            searchPlaceholder="Buscar contas"
            emptyLabel="Nenhuma conta AWS disponível"
            disabled={!initialized}
          />
          {initialized && accounts.length > 0 && !hasAccountSelection && (
            <div className={styles.accountHint} role="status">
              Selecione ao menos uma conta para consultar os custos.
            </div>
          )}
        </div>
      </Section>

      <Section
        title="Filtros"
        description="Refine período, perfil e metodologia para o escopo de contas selecionado."
      >
        <FilterBar
          actions={hasOverrides ? (
            <Button
              variant="ghost"
              size="sm"
              leadingIcon={<RotateCcw {...iconDefaults} />}
              onClick={restoreProfile}
            >
              Restaurar perfil
            </Button>
          ) : undefined}
        >
          <Select
            label="Perfil"
            value={profileId}
            disabled={!initialized || profiles.length === 0}
            options={profiles.map((profile) => ({
              value: profile.id,
              label: `${profile.name}${profile.is_default ? " · padrão" : ""}`,
            }))}
            onChange={(event) => chooseProfile(event.target.value)}
            controlSize="sm"
          />
          <DateRangePicker
            value={dateRangeValue}
            onChange={setDateRange}
            presets={BILLING_PERIOD_PRESETS.map((preset) => ({ value: preset.value, label: preset.label }))}
            presetValue={periodPreset}
            onPresetChange={(nextPreset) => {
              if (VALID_PRESETS.has(nextPreset as BillingPeriodPreset)) {
                setPeriodPreset(nextPreset as BillingPeriodPreset);
              } else {
                setPeriodPreset("custom");
              }
            }}
            presetLabel="Período"
            presetPlaceholder="Escolha um período"
            startLabel="Data inicial"
            endLabel="Data final"
            clearLabel="Limpar datas"
            maxDate={today}
            clearable={periodPreset === "custom"}
          />
          <Select
            label="Métrica"
            value={metric}
            options={(Object.keys(METRIC_LABELS) as BillingMetric[]).map((value) => ({
              value,
              label: METRIC_LABELS[value],
            }))}
            onChange={(event) => setMetric(event.target.value as BillingMetric)}
            controlSize="sm"
          />
          <Select
            label="Granularidade"
            value={granularity}
            options={(Object.keys(GRANULARITY_LABELS) as BillingGranularity[]).map((value) => ({
              value,
              label: GRANULARITY_LABELS[value],
            }))}
            onChange={(event) => setGranularity(event.target.value as BillingGranularity)}
            controlSize="sm"
          />
          <Select
            label="Agrupamento"
            value={groupBy}
            options={(Object.keys(GROUP_BY_LABELS) as BillingGroupBy[]).map((value) => ({
              value,
              label: GROUP_BY_LABELS[value],
            }))}
            onChange={(event) => setGroupBy(event.target.value as BillingGroupBy)}
            controlSize="sm"
          />
        </FilterBar>

        {periodPreset === "custom" && !period && (
          <Alert
            variant="warning"
            title="Período personalizado incompleto"
            description="Informe um intervalo válido, sem datas futuras."
          />
        )}

        {selectedProfile && (
          <div className={styles.profileContext}>
            <div>
              <span>Perfil aplicado</span>
              <strong>{selectedProfile.name}{selectedProfile.is_default ? " · padrão" : ""}</strong>
            </div>
            <p>{profileSummary(selectedProfile)}</p>
            {hasOverrides && <Badge variant="warning">Consulta com override temporário</Badge>}
          </div>
        )}

        <details className={styles.advancedFilters}>
          <summary>Mais filtros</summary>
          <div className={styles.advancedContent}>
            <div className={styles.advancedHeading}>
              <strong>Excluir tipos de registro</strong>
              {!sameStringSet(excludeRecordTypes, selectedProfile?.exclude_record_types || []) && (
                <Badge variant="warning">Sobrescrito</Badge>
              )}
            </div>
            <div className={styles.recordTypeGrid}>
              {AWS_RECORD_TYPES.map((recordType) => (
                <Checkbox
                  key={recordType}
                  checked={excludeRecordTypes.includes(recordType)}
                  onChange={(event) => toggleRecordType(recordType, event.target.checked)}
                  label={recordType}
                />
              ))}
            </div>
          </div>
        </details>
      </Section>

      {queryMetadata && (
        <div className={styles.queryMetadata}>
          <strong>Consulta atual:</strong>
          <span>{queryMetadata}</span>
        </div>
      )}

      {!hasAccountSelection ? (
        <Section appearance="card">
          <DataState
            empty
            emptyTitle="Selecione uma ou mais contas"
            emptyDescription="Selecione ao menos uma conta para consultar os custos. Nenhuma consulta ao Cost Explorer é executada enquanto a seleção estiver vazia."
          >
            <span />
          </DataState>
        </Section>
      ) : (
        <div className={styles.analysis}>
          <Section
            title="Resumo financeiro"
            description={period && previousPeriod
              ? `Comparação: ${formatBillingRange(previousPeriod)} → ${formatBillingRange(period)}`
              : "Resumo do período selecionado."}
          >
            {summary.loading ? (
              <div className={styles.metricGrid}>
                <MetricCard label="Custo do período" value={null} loading />
                <MetricCard label="Custo do período" value={null} loading />
                <MetricCard label="Custo do período" value={null} loading />
              </div>
            ) : summary.error ? (
              <Alert variant="danger" title="Falha ao carregar o resumo financeiro" description={summary.error} />
            ) : summary.data?.totals.length ? (
              <div className={styles.metricGrid}>
                {summary.data.totals.map((total) => {
                  const previous = previousSummary.data?.totals.find((item) => item.currency === total.currency);
                  const trend = previous ? variationTrend(total.amount, previous.amount) : null;
                  const comparisonText = previousSummary.loading
                    ? "Carregando comparação com o período anterior…"
                    : previousSummary.error
                      ? "Comparação com o período anterior indisponível."
                      : previous
                        ? (
                            <>
                              Anterior:{" "}
                              <CurrencyDisplay
                                value={numericAmount(previous.amount)}
                                currency={previous.currency}
                                locale="pt-BR"
                                currencyDisplay="code"
                                minimumFractionDigits={2}
                                maximumFractionDigits={2}
                              />
                            </>
                          )
                        : "Período anterior sem valor na mesma moeda/unidade.";
                  const variationText = previous ? variationSupportingText(total.amount, previous.amount) : null;
                  return (
                    <MetricCard
                      key={total.currency}
                      label={`Custo do período · ${total.currency}`}
                      value={(
                        <CurrencyDisplay
                          value={numericAmount(total.amount)}
                          currency={total.currency}
                          locale="pt-BR"
                          currencyDisplay="code"
                          minimumFractionDigits={2}
                          maximumFractionDigits={2}
                        />
                      )}
                      trend={trend || undefined}
                      status={(
                        <StatusIndicator
                          status={statusSemantic(total.status)}
                          label={billingStatusLabel(total.status)}
                        />
                      )}
                      supportingText={variationText || comparisonText}
                    />
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title="Nenhum custo encontrado"
                description="Nenhum custo foi retornado para o período e os filtros selecionados."
              />
            )}
          </Section>

          <ChartCard
            title="Evolução de custos"
            description={timeseries.data
              ? `${GRANULARITY_LABELS[timeseries.data.granularity]} · ${GROUP_BY_LABELS[timeseries.data.group_by]}`
              : "Acompanhe a evolução temporal e a composição do custo."}
            loading={timeseries.loading}
            error={timeseries.error || undefined}
            empty={Boolean(timeseries.data) && timeseries.data!.points.length === 0}
            emptyTitle="Nenhum custo no período"
            emptyDescription="Não há pontos de custo para os filtros selecionados."
          >
            <div className={styles.chartStack}>
              {timeseries.data && chartDatasets.map((dataset) => (
                <BillingCostChart
                  key={dataset.currency}
                  dataset={dataset}
                  granularity={timeseries.data!.granularity}
                  groupBy={timeseries.data!.group_by}
                />
              ))}
            </div>
          </ChartCard>

          <div className={styles.breakdownLayout}>
            <Section
              title="Custo por serviço"
              description="Detalhamento preciso dos serviços com maior impacto no período."
              appearance="card"
            >
              <DataState
                loading={serviceBreakdown.loading}
                error={serviceBreakdown.error || undefined}
                empty={Boolean(serviceBreakdown.data) && serviceBreakdown.data!.items.length === 0}
                emptyTitle="Nenhum serviço com custo"
                emptyDescription="Nenhum serviço com custo foi retornado para esta consulta."
              >
                {serviceBreakdown.data?.items.length
                  ? <BreakdownTable items={serviceBreakdown.data.items} kind="service" />
                  : <span />}
              </DataState>
            </Section>

            {selectedAccountIds.length > 1 && (
              <Section
                title="Custo por conta"
                description="Compare a concentração do custo entre as contas selecionadas."
                appearance="card"
              >
                <DataState
                  loading={accountBreakdown.loading}
                  error={accountBreakdown.error || undefined}
                  empty={Boolean(accountBreakdown.data) && accountBreakdown.data!.items.length === 0}
                  emptyTitle="Nenhum custo por conta"
                  emptyDescription="Nenhum custo por conta foi retornado para esta consulta."
                >
                  {accountBreakdown.data?.items.length
                    ? <BreakdownTable items={accountBreakdown.data.items} kind="account" />
                    : <span />}
                </DataState>
              </Section>
            )}
          </div>
        </div>
      )}

      <p className={styles.disclaimer}>
        Os valores exibidos vêm do AWS Cost Explorer, preservam a moeda/unidade retornada pela AWS e podem sofrer atraso de processamento. Nenhuma conversão cambial é realizada. Forecast e estimativas são identificados apenas quando informados pelo contrato de dados.
      </p>
    </div>
  );
}
