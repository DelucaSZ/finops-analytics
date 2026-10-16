"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, RotateCcw, Settings2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
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
  BillingGranularity,
  BillingMetric,
  BillingProfile,
  BillingSeriesPoint,
  BillingSummaryResponse,
  BillingTimeSeriesResponse,
} from "@/lib/billing";
import {
  BILLING_PERIOD_PRESETS,
  areAllBillingAccountsSelected,
  billingAccountIdsForSelectAll,
  billingQuerySignature,
  billingVariation,
  formatBillingDate,
  formatBillingMoney,
  formatBillingRange,
  groupBillingByCurrency,
  hasBillingAccountSelection,
  inclusiveEndDate,
  parseBillingAccountIds,
  previousEquivalentPeriod,
  resolveBillingPeriod,
  sameStringSet,
  topBillingItems,
} from "@/lib/billing-dashboard.mjs";
import type { BillingPeriod, BillingPeriodPreset } from "@/lib/billing-dashboard.mjs";
import type { CloudAccount } from "@/lib/types";
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

function accountLabel(account: CloudAccount) {
  return account.name
    ? `${account.name} · ${account.native_account_id}`
    : account.native_account_id;
}

function profileSummary(profile: BillingProfile) {
  const excluded = profile.exclude_record_types.length
    ? `Exclui ${profile.exclude_record_types.join(", ")}`
    : "Sem exclusões por tipo";
  return `${GRANULARITY_LABELS[profile.granularity]} · ${METRIC_LABELS[profile.metric]} · ${excluded}`;
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
  if (!sameStringSet(excludeRecordTypes, profile.exclude_record_types)) {
    request.exclude_record_types = excludeRecordTypes;
  }
  return request;
}

function formatVariation(current: string, previous: string) {
  const variation = billingVariation(current, previous);
  if (variation.kind === "new") return "Novo custo no período";
  if (variation.kind === "unavailable" || variation.percent === null) return "Variação não aplicável";
  const prefix = variation.percent > 0 ? "+" : "";
  return `${prefix}${variation.percent.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
}

function SectionStatus({ loading, error, empty, emptyText }: {
  loading: boolean;
  error: string;
  empty: boolean;
  emptyText: string;
}) {
  if (loading) return <div className={styles.sectionState} role="status">Carregando dados de Billing…</div>;
  if (error) return <div className={styles.sectionError} role="alert">{error}</div>;
  if (empty) return <div className={styles.sectionState}>{emptyText}</div>;
  return null;
}

function BillingCostChart({ points, currency, granularity }: {
  points: BillingSeriesPoint[];
  currency: string;
  granularity: BillingGranularity;
}) {
  if (!points.length) return null;
  const width = 920;
  const height = 300;
  const padX = 52;
  const padY = 34;
  const values = points.map((point) => Number(point.amount)).filter(Number.isFinite);
  const minimum = Math.min(0, ...values);
  const maximum = Math.max(0, ...values);
  const span = maximum - minimum || 1;
  const innerWidth = width - padX * 2;
  const innerHeight = height - padY * 2;
  const x = (index: number) => padX + (points.length === 1 ? innerWidth / 2 : (index / (points.length - 1)) * innerWidth);
  const y = (value: number) => padY + ((maximum - value) / span) * innerHeight;
  const zeroY = y(0);
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${x(index)} ${y(Number(point.amount))}`)
    .join(" ");
  const estimated = points.some((point) => point.estimated);
  const first = points[0];
  const last = points[points.length - 1];

  return (
    <div className={styles.chartGroup}>
      <div className={styles.chartMeta}>
        <strong>{currency}</strong>
        <span>{granularity === "DAILY" ? "Dia a dia" : "Mês a mês"}</span>
        {estimated && <span className={styles.estimatedBadge}>Inclui dados estimados</span>}
      </div>
      <div className={styles.chartScroll}>
        <svg
          className={styles.chart}
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`Evolução de custos em ${currency}. ${estimated ? "Inclui dados estimados." : "Dados não marcados como estimados."}`}
        >
          <line x1={padX} x2={width - padX} y1={zeroY} y2={zeroY} className={styles.axisLine} />
          <path d={path} className={styles.costLine} />
          {points.map((point, index) => (
            <g key={`${point.start_date}-${point.currency}`}>
              <circle
                cx={x(index)}
                cy={y(Number(point.amount))}
                r={point.estimated ? 5 : 4}
                className={point.estimated ? styles.estimatedPoint : styles.costPoint}
              >
                <title>{`${formatBillingDate(point.start_date)} · ${formatBillingMoney(point.amount, point.currency)}${point.estimated ? " · Estimado" : ""}`}</title>
              </circle>
              {point.estimated && (
                <text x={x(index)} y={y(Number(point.amount)) - 10} textAnchor="middle" className={styles.estimatedMark}>*</text>
              )}
            </g>
          ))}
          <text x={padX} y={height - 8} className={styles.axisLabel}>{formatBillingDate(first.start_date)}</text>
          <text x={width - padX} y={height - 8} textAnchor="end" className={styles.axisLabel}>{formatBillingDate(last.start_date)}</text>
        </svg>
      </div>
      {estimated && <p className={styles.chartNote}>* Bucket marcado como estimado pelo AWS Cost Explorer.</p>}
    </div>
  );
}

function BreakdownTable({ items, kind }: {
  items: BillingBreakdownItem[];
  kind: "service" | "account";
}) {
  const groups = groupBillingByCurrency(items);
  return (
    <div className={styles.breakdownGroups}>
      {groups.map(([currency, currencyItems]) => {
        const topItems = topBillingItems(currencyItems, 10);
        return (
          <div key={currency} className={styles.breakdownGroup}>
            <div className={styles.currencyHeading}>
              <strong>{currency}</strong>
              <span>Top {Math.min(10, currencyItems.length)} de {currencyItems.length}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{kind === "service" ? "Serviço" : "Conta"}</th>
                    {kind === "account" && <th>AWS Account ID</th>}
                    <th>Valor</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {topItems.map((item) => (
                    <tr key={`${currency}-${item.key}`}>
                      <td>
                        <strong>{kind === "account" ? (item.display_name || item.label || item.key) : (item.label || item.key)}</strong>
                      </td>
                      {kind === "account" && <td><code>{item.aws_account_id || item.key}</code></td>}
                      <td>{formatBillingMoney(item.amount, item.currency)}</td>
                      <td>{item.estimated ? <span className={styles.estimatedBadge}>Estimado</span> : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
  const allAccountsSelected = areAllBillingAccountsSelected(
    accounts.map((account) => account.id),
    selectedAccountIds,
  );
  const hasOverrides = Boolean(
    selectedProfile
    && (
      selectedProfile.metric !== metric
      || selectedProfile.granularity !== granularity
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
      excludeRecordTypes,
      revision: refreshRevision,
    }),
    [excludeRecordTypes, granularity, metric, period, profileId, refreshRevision, selectedAccountIds],
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
      excludeRecordTypes,
    );
    const comparisonRequest = buildRequest(
      selectedProfile,
      selectedAccountIds,
      previousPeriod,
      granularity,
      metric,
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
        if (active() && !isAbort(error)) setSummary({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo do período.") });
      });

    getAwsBillingSummary(comparisonRequest, controller.signal)
      .then((data) => { if (active()) setPreviousSummary({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) setPreviousSummary({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o período anterior.") });
      });

    getAwsBillingTimeSeries(currentRequest, controller.signal)
      .then((data) => { if (active()) setTimeseries({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) setTimeseries({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar a evolução de custos.") });
      });

    getAwsBillingBreakdown({ ...currentRequest, group_by: "SERVICE" }, controller.signal)
      .then((data) => { if (active()) setServiceBreakdown({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) setServiceBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo por serviço.") });
      });

    if (selectedAccountIds.length > 1) {
      getAwsBillingBreakdown({ ...currentRequest, group_by: "ACCOUNT" }, controller.signal)
        .then((data) => { if (active()) setAccountBreakdown({ data, loading: false, error: "" }); })
        .catch((error) => {
          if (active() && !isAbort(error)) setAccountBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "Falha ao carregar o custo por conta.") });
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
    setExcludeRecordTypes(profile.exclude_record_types);
  }

  function restoreProfile() {
    if (!selectedProfile) return;
    setMetric(selectedProfile.metric);
    setGranularity(selectedProfile.granularity);
    setExcludeRecordTypes(selectedProfile.exclude_record_types);
  }

  function toggleAccount(accountId: number, checked: boolean) {
    setSelectedAccountIds((current) => {
      if (checked) return Array.from(new Set([...current, accountId])).sort((a, b) => a - b);
      return current.filter((value) => value !== accountId);
    });
  }

  function toggleRecordType(recordType: string, checked: boolean) {
    setExcludeRecordTypes((current) => {
      if (checked) return Array.from(new Set([...current, recordType])).sort();
      return current.filter((value) => value !== recordType);
    });
  }

  const queryMetadata = hasAccountSelection && selectedProfile && period
    ? `${selectedAccountIds.length} ${selectedAccountIds.length === 1 ? "conta" : "contas"} · ${formatBillingRange(period)} · ${GRANULARITY_LABELS[granularity]} · ${METRIC_LABELS[metric]} · ${excludeRecordTypes.length ? `Exclui ${excludeRecordTypes.join(", ")}` : "Sem exclusões"}`
    : "";
  const anyLoading = summary.loading || previousSummary.loading || timeseries.loading || serviceBreakdown.loading || accountBreakdown.loading;
  const timeSeriesGroups = timeseries.data ? groupBillingByCurrency(timeseries.data.points) : [];
  const today = localTodayKey();

  return (
    <>
      <PageHeader
        eyebrow="BILLING · AWS"
        title="Billing"
        description="Consulte custos do AWS Cost Explorer por período, conta, metodologia e perfil. Valores atuais podem estar estimados e não são apresentados como fatura final."
        actions={
          <>
            {role === "admin" && (
              <Link className="button ghost" href="/settings/billing/profiles">
                <Settings2 size={16} /> Gerenciar perfis
              </Link>
            )}
            <button
              className="button ghost"
              type="button"
              disabled={!initialized || !hasAccountSelection || !period || anyLoading}
              onClick={() => setRefreshRevision((value) => value + 1)}
            >
              <RefreshCw size={16} /> Atualizar
            </button>
          </>
        }
      />

      {bootstrapError && <div className="alert error" role="alert">{bootstrapError}</div>}

      <section className={`panel ${styles.filtersPanel}`} aria-labelledby="billing-filters-title">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">CONSULTA</div>
            <h2 id="billing-filters-title">Filtros de Billing</h2>
          </div>
          {hasOverrides && (
            <button className="button ghost small" type="button" onClick={restoreProfile}>
              <RotateCcw size={15} /> Restaurar perfil
            </button>
          )}
        </div>
        <div className={styles.filtersBody}>
          <div className={styles.primaryFilters}>
            <label className={styles.field}>
              <span>Perfil</span>
              <select value={profileId} disabled={!initialized || !profiles.length} onChange={(event) => chooseProfile(event.target.value)}>
                {profiles.map((profile) => <option key={profile.id} value={profile.id}>{profile.name}{profile.is_default ? " · padrão" : ""}</option>)}
              </select>
            </label>

            <label className={styles.field}>
              <span>Período</span>
              <select value={periodPreset} onChange={(event) => setPeriodPreset(event.target.value as BillingPeriodPreset)}>
                {BILLING_PERIOD_PRESETS.map((preset) => <option key={preset.value} value={preset.value}>{preset.label}</option>)}
              </select>
            </label>

            <label className={styles.field}>
              <span>Métrica {selectedProfile?.metric !== metric && <em>Sobrescrito</em>}</span>
              <select value={metric} onChange={(event) => setMetric(event.target.value as BillingMetric)}>
                {(Object.keys(METRIC_LABELS) as BillingMetric[]).map((value) => <option key={value} value={value}>{METRIC_LABELS[value]}</option>)}
              </select>
            </label>

            <label className={styles.field}>
              <span>Granularidade {selectedProfile?.granularity !== granularity && <em>Sobrescrito</em>}</span>
              <select value={granularity} onChange={(event) => setGranularity(event.target.value as BillingGranularity)}>
                {(Object.keys(GRANULARITY_LABELS) as BillingGranularity[]).map((value) => <option key={value} value={value}>{GRANULARITY_LABELS[value]}</option>)}
              </select>
            </label>
          </div>

          {periodPreset === "custom" && (
            <div className={styles.customDates}>
              <label className={styles.field}>
                <span>Data inicial</span>
                <input type="date" value={customFrom} max={today} onChange={(event) => setCustomFrom(event.target.value)} />
              </label>
              <label className={styles.field}>
                <span>Data final</span>
                <input type="date" value={customTo} max={today} onChange={(event) => setCustomTo(event.target.value)} />
              </label>
              {!period && <p className={styles.validationMessage}>Informe um intervalo válido, sem datas futuras.</p>}
            </div>
          )}

          {selectedProfile && (
            <div className={styles.profileContext}>
              <div><span>Perfil aplicado</span><strong>{selectedProfile.name}{selectedProfile.is_default ? " · padrão" : ""}</strong></div>
              <p>{profileSummary(selectedProfile)}</p>
              {hasOverrides && <span className={styles.overrideBadge}>Consulta com override temporário</span>}
            </div>
          )}

          <fieldset className={styles.accountPicker}>
            <legend>Contas AWS</legend>
            <label className={styles.allAccounts}>
              <input
                type="checkbox"
                checked={allAccountsSelected}
                disabled={!accounts.length}
                onChange={(event) => setSelectedAccountIds(
                  billingAccountIdsForSelectAll(
                    event.target.checked,
                    accounts.map((account) => account.id),
                  ),
                )}
              />
              <span><strong>Todas as contas</strong><small>Todas as contas AWS cadastradas e disponíveis ao usuário atual.</small></span>
            </label>
            <div className={styles.accountGrid}>
              {accounts.map((account) => (
                <label key={account.id} className={styles.accountOption}>
                  <input
                    type="checkbox"
                    checked={selectedAccountIds.includes(account.id)}
                    onChange={(event) => toggleAccount(account.id, event.target.checked)}
                  />
                  <span><strong>{account.name || "Conta AWS"}</strong><small>{account.native_account_id}</small></span>
                </label>
              ))}
            </div>
            {!accounts.length && initialized && <p className={styles.validationMessage}>Nenhuma conta AWS cadastrada está disponível para Billing.</p>}
            {accounts.length > 0 && !hasAccountSelection && <p className={styles.validationMessage}>Selecione ao menos uma conta.</p>}
          </fieldset>

          <details className={styles.advancedFilters}>
            <summary>Mais filtros</summary>
            <div>
              <div className={styles.advancedHeading}>
                <strong>Excluir tipos de registro</strong>
                {!sameStringSet(excludeRecordTypes, selectedProfile?.exclude_record_types || []) && <span className={styles.overrideBadge}>Sobrescrito</span>}
              </div>
              <div className={styles.recordTypeGrid}>
                {AWS_RECORD_TYPES.map((recordType) => (
                  <label key={recordType}>
                    <input type="checkbox" checked={excludeRecordTypes.includes(recordType)} onChange={(event) => toggleRecordType(recordType, event.target.checked)} />
                    {recordType}
                  </label>
                ))}
              </div>
            </div>
          </details>
        </div>
      </section>

      {queryMetadata && <div className={styles.queryMetadata}><strong>Consulta:</strong> {queryMetadata}</div>}

      {!hasAccountSelection ? (
        <section className={`panel ${styles.dataPanel}`} aria-live="polite">
          <div className={styles.panelBody}>
            <div className={styles.sectionState}>Selecione ao menos uma conta para consultar os custos.</div>
          </div>
        </section>
      ) : (
        <>
      <section aria-labelledby="billing-summary-title">
        <div className={styles.sectionHeading}>
          <div><span className="eyebrow">RESUMO</span><h2 id="billing-summary-title">Custo do período</h2></div>
          {period && previousPeriod && <span>Comparação: {formatBillingRange(previousPeriod)} → {formatBillingRange(period)}</span>}
        </div>
        <SectionStatus
          loading={summary.loading}
          error={summary.error}
          empty={!summary.loading && !summary.error && Boolean(summary.data) && summary.data!.totals.length === 0}
          emptyText="Nenhum custo encontrado para o período e filtros selecionados."
        />
        {summary.data?.totals.length ? (
          <div className={styles.kpiGrid}>
            {summary.data.totals.map((total) => {
              const previous = previousSummary.data?.totals.find((item) => item.currency === total.currency);
              return (
                <article key={total.currency} className={styles.kpiCard}>
                  <div className={styles.kpiHeading}>
                    <span>Custo do período · {total.currency}</span>
                    {total.estimated && <span className={styles.estimatedBadge}>Estimado</span>}
                  </div>
                  <strong>{formatBillingMoney(total.amount, total.currency)}</strong>
                  <div className={styles.comparisonBlock}>
                    {previousSummary.loading ? (
                      <span>Carregando comparação…</span>
                    ) : previousSummary.error ? (
                      <span>Comparação indisponível</span>
                    ) : previous ? (
                      <>
                        <span>Anterior: {formatBillingMoney(previous.amount, previous.currency)}{previous.estimated ? " · estimado" : ""}</span>
                        <b>{formatVariation(total.amount, previous.amount)}</b>
                      </>
                    ) : (
                      <span>Período anterior sem valor na mesma moeda/unidade.</span>
                    )}
                  </div>
                  {total.estimated && <small>Inclui dados estimados pelo AWS Cost Explorer.</small>}
                </article>
              );
            })}
          </div>
        ) : null}
      </section>

      <section className={`panel ${styles.dataPanel}`} aria-labelledby="billing-timeseries-title">
        <div className="panel-heading">
          <div><div className="eyebrow">TENDÊNCIA</div><h2 id="billing-timeseries-title">Evolução de custos</h2></div>
          {timeseries.data && <span className={styles.panelMeta}>{GRANULARITY_LABELS[timeseries.data.granularity]}</span>}
        </div>
        <div className={styles.panelBody}>
          <SectionStatus
            loading={timeseries.loading}
            error={timeseries.error}
            empty={!timeseries.loading && !timeseries.error && Boolean(timeseries.data) && timeseries.data!.points.length === 0}
            emptyText="Nenhum ponto de custo encontrado para o período selecionado."
          />
          {timeSeriesGroups.map(([currency, points]) => (
            <BillingCostChart key={currency} currency={currency} points={points} granularity={timeseries.data!.granularity} />
          ))}
        </div>
      </section>

      <div className={styles.breakdownLayout}>
        <section className={`panel ${styles.dataPanel}`} aria-labelledby="billing-service-title">
          <div className="panel-heading"><div><div className="eyebrow">BREAKDOWN</div><h2 id="billing-service-title">Custo por serviço</h2></div></div>
          <div className={styles.panelBody}>
            <SectionStatus
              loading={serviceBreakdown.loading}
              error={serviceBreakdown.error}
              empty={!serviceBreakdown.loading && !serviceBreakdown.error && Boolean(serviceBreakdown.data) && serviceBreakdown.data!.items.length === 0}
              emptyText="Nenhum serviço com custo foi retornado para esta consulta."
            />
            {serviceBreakdown.data?.items.length ? <BreakdownTable items={serviceBreakdown.data.items} kind="service" /> : null}
          </div>
        </section>

        {selectedAccountIds.length > 1 && (
          <section className={`panel ${styles.dataPanel}`} aria-labelledby="billing-account-title">
            <div className="panel-heading"><div><div className="eyebrow">BREAKDOWN</div><h2 id="billing-account-title">Custo por conta</h2></div></div>
            <div className={styles.panelBody}>
              <SectionStatus
                loading={accountBreakdown.loading}
                error={accountBreakdown.error}
                empty={!accountBreakdown.loading && !accountBreakdown.error && Boolean(accountBreakdown.data) && accountBreakdown.data!.items.length === 0}
                emptyText="Nenhum custo por conta foi retornado para esta consulta."
              />
              {accountBreakdown.data?.items.length ? <BreakdownTable items={accountBreakdown.data.items} kind="account" /> : null}
            </div>
          </section>
        )}
      </div>
        </>
      )}

      <p className={styles.disclaimer}>
        Os valores exibidos vêm do AWS Cost Explorer, preservam a moeda/unidade retornada pela AWS e podem sofrer atraso de processamento. Nenhuma conversão cambial é realizada. Billing e Fluxo permanecem domínios independentes.
      </p>
    </>
  );
}
