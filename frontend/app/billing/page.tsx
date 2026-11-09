"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, RotateCcw, Settings2 } from "lucide-react";
import {
  AccountSelector,
  ChartCard,
  CurrencyDisplay,
  DataState,
  DateRangePicker,
  FilterBar,
  FilterItem,
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

const METRIC_LABELS = { AMORTIZED_COST: "metrics.amortized", NET_AMORTIZED_COST: "metrics.netAmortized", UNBLENDED_COST: "metrics.unblended" } as const satisfies Record<BillingMetric, string>;

const GRANULARITY_LABELS = { DAILY: "granularity.daily", MONTHLY: "granularity.monthly" } as const satisfies Record<BillingGranularity, string>;

const GROUP_BY_LABELS = { NONE: "group.none", SERVICE: "filters.service", ACCOUNT: "filters.account" } as const satisfies Record<BillingGroupBy, string>;

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

function profileSummary(profile: BillingProfile, metrics: Record<BillingMetric, string>, granularity: Record<BillingGranularity, string>, groups: Record<BillingGroupBy, string>, excluded: string) {
  return `${granularity[profile.granularity]} · ${metrics[profile.metric]} · ${groups[profile.group_by]} · ${excluded}`;
}

// Store stable error keys rather than localized strings so language switches update visible errors.
function billingErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "ACCESS_DENIED": return "errors.accessDenied";
      case "COST_EXPLORER_UNAVAILABLE": return "errors.costExplorerUnavailable";
      case "INVALID_BILLING_SCOPE": return "errors.invalidScope";
      case "THROTTLED": return "errors.throttled";
      case "ACCOUNT_NOT_FOUND": return "errors.accountUnavailable";
      case "INVALID_PERIOD": return "errors.invalidPeriod";
      case "UPSTREAM_DATA_INVALID": return "errors.upstreamData";
      case "UPSTREAM_ERROR": return "errors.upstream";
      case "ACCOUNT_NOT_AWS": return "errors.accountUnavailable";
      default: return fallback;
    }
  }
  return fallback;
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

function variationTrend(current: string, previous: string, label: string, locale: string) {
  const variation = billingVariation(current, previous);
  if (variation.kind !== "percent" || variation.percent === null) return null;
  const direction = variation.percent > 0 ? "up" : variation.percent < 0 ? "down" : "flat";
  const sentiment = variation.percent > 0 ? "negative" : variation.percent < 0 ? "positive" : "neutral";
  return {
    value: variation.percent,
    direction,
    sentiment,
    label,
    locale,
  } as const;
}

function variationSupportingText(current: string, previous: string, newText: string, unavailableText: string) {
  const variation = billingVariation(current, previous);
  if (variation.kind === "new") return newText;
  if (variation.kind === "unavailable") return unavailableText;
  return null;
}

const PERIOD_LABELS = {
  this_month: "periods.thisMonth", previous_month: "periods.previousMonth", last_30_days: "periods.last30Days", last_3_months: "periods.last3Months", last_6_months: "periods.last6Months", this_year: "periods.thisYear", custom: "periods.custom",
} as const satisfies Record<BillingPeriodPreset, string>;
function billingStatusKey(status: BillingDataStatus) {
  switch (status) {
    case "ESTIMATED": return "status.estimated";
    case "PARTIALLY_ESTIMATED": return "status.partial";
    case "FORECAST": return "status.forecast";
    case "INCLUDES_FORECAST": return "status.includesForecast";
    default: return "status.actual";
  }
}

function BreakdownTable({
  items,
  kind,
}: {
  items: BillingBreakdownItem[];
  kind: "service" | "account";
}) {
  const t = useTranslations("billing");
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
                  <TableHead>{kind === "service" ? t("filters.service") : t("filters.account")}</TableHead>
                  {kind === "account" && <TableHead>AWS Account ID</TableHead>}
                  <TableHead numeric>{t("breakdown.share")}</TableHead>
                  <TableHead numeric>{t("breakdown.amount")}</TableHead>
                  <TableHead>{t("breakdown.state")}</TableHead>
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
                        <PercentageDisplay value={share}  maximumFractionDigits={1} />
                      </TableCell>
                      <TableCell numeric>
                        <CurrencyDisplay
                          value={amount}
                          currency={item.currency}
                          
                          currencyDisplay="code"
                          minimumFractionDigits={2}
                          maximumFractionDigits={2}
                        />
                      </TableCell>
                      <TableCell>
                        <StatusIndicator
                          status={statusSemantic(item.status)}
                          label={t(billingStatusKey(item.status))}
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
  const t = useTranslations("billing");
  const locale = useLocale();
  const metricLabels = { AMORTIZED_COST: t("metrics.amortized"), NET_AMORTIZED_COST: t("metrics.netAmortized"), UNBLENDED_COST: t("metrics.unblended") };
  const granularityLabels = { DAILY: t("granularity.daily"), MONTHLY: t("granularity.monthly") };
  const groupLabels = { NONE: t("group.none"), SERVICE: t("filters.service"), ACCOUNT: t("filters.account") };
  const errorLabel = (key: string) => {
    switch (key) {
      case "errors.accessDenied": return t("errors.accessDenied");
      case "errors.costExplorerUnavailable": return t("errors.costExplorerUnavailable");
      case "errors.invalidScope": return t("errors.invalidScope");
      case "errors.throttled": return t("errors.throttled");
      case "errors.accountUnavailable": return t("errors.accountUnavailable");
      case "errors.invalidPeriod": return t("errors.invalidPeriod");
      case "errors.upstreamData": return t("errors.upstreamData");
      case "errors.upstream": return t("errors.upstream");
      case "errors.bootstrap": return t("errors.bootstrap");
      case "errors.summary": return t("errors.summary");
      case "errors.previous": return t("errors.previous");
      case "errors.timeseries": return t("errors.timeseries");
      case "errors.service": return t("errors.service");
      case "errors.account": return t("errors.account");
      case "errors.generic": return t("errors.generic");
      default: return t("errors.generic");
    }
  };
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
      label: account.name || t("filters.awsAccount"),
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
          setBootstrapError("errors.noEnabledProfile");
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
          setBootstrapError(billingErrorMessage(error, "errors.bootstrap"));
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
          setSummary({ data: null, loading: false, error: billingErrorMessage(error, "errors.summary") });
        }
      });

    getAwsBillingSummary(comparisonRequest, controller.signal)
      .then((data) => { if (active()) setPreviousSummary({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setPreviousSummary({ data: null, loading: false, error: billingErrorMessage(error, "errors.previous") });
        }
      });

    getAwsBillingTimeSeries(currentRequest, controller.signal)
      .then((data) => { if (active()) setTimeseries({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setTimeseries({ data: null, loading: false, error: billingErrorMessage(error, "errors.timeseries") });
        }
      });

    getAwsBillingBreakdown({ ...currentRequest, group_by: "SERVICE" }, controller.signal)
      .then((data) => { if (active()) setServiceBreakdown({ data, loading: false, error: "" }); })
      .catch((error) => {
        if (active() && !isAbort(error)) {
          setServiceBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "errors.service") });
        }
      });

    if (selectedAccountIds.length > 1) {
      getAwsBillingBreakdown({ ...currentRequest, group_by: "ACCOUNT" }, controller.signal)
        .then((data) => { if (active()) setAccountBreakdown({ data, loading: false, error: "" }); })
        .catch((error) => {
          if (active() && !isAbort(error)) {
            setAccountBreakdown({ data: null, loading: false, error: billingErrorMessage(error, "errors.account") });
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
    ? t("filters.query", { count: selectedAccountIds.length, period: formatBillingRange(period, locale), granularity: granularityLabels[granularity], grouping: groupLabels[groupBy], metric: metricLabels[metric], exclusions: excludeRecordTypes.length ? t("filters.excluded", {types: excludeRecordTypes.join(", ")}) : t("filters.noExclusions") })
    : "";
  const anyLoading = summary.loading || previousSummary.loading || timeseries.loading || serviceBreakdown.loading || accountBreakdown.loading;
  const today = localTodayKey();
  const dateRangeValue: DateRangeValue = periodPreset === "custom"
    ? { startDate: customFrom || null, endDate: customTo || null }
    : {
        startDate: period?.start_date || null,
        endDate: period ? inclusiveEndDate(period.end_date) : null,
      };
  const periodPicker = (
    <DateRangePicker
      value={dateRangeValue}
      onChange={setDateRange}
      presets={BILLING_PERIOD_PRESETS.map((preset) => ({ value: preset.value, label: t(PERIOD_LABELS[preset.value]) }))}
      presetValue={periodPreset}
      onPresetChange={(nextPreset) => {
        if (VALID_PRESETS.has(nextPreset as BillingPeriodPreset)) {
          setPeriodPreset(nextPreset as BillingPeriodPreset);
        } else {
          setPeriodPreset("custom");
        }
      }}
      presetLabel={t("filters.period")}
      presetPlaceholder={t("filters.choosePeriod")}
      startLabel={t("filters.start")}
      endLabel={t("filters.end")}
      clearLabel={t("filters.clearDates")}
      maxDate={today}
      clearable={periodPreset === "custom"}
      layout={periodPreset === "custom" ? "inline" : undefined}
    />
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        metadata={(
          <div className={styles.headerMetadata}>
            <ProviderBadge provider="aws" />
            <span>
              {selectedAccountIds.length === 0
                ? t("empty.noSelected")
                : t("filters.selected", {count: selectedAccountIds.length})}
            </span>
          </div>
        )}
        actions={(
          <>
            {role === "admin" && (
              <Link className={styles.actionLink} href="/settings/billing/profiles">
                <Settings2 {...iconDefaults} aria-hidden="true" />
                <span>{t("actions.manageProfiles")}</span>
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
              {t("actions.refresh")}
            </Button>
          </>
        )}
      />

      {bootstrapError && (
        <Alert variant="danger" title={t("errors.bootstrapTitle")} description={errorLabel(bootstrapError)} />
      )}

      <Section
        title={t("sections.accounts")}
        description={t("sections.accountsDescription")}
      >
        <div className={styles.accountContext}>
          <AccountSelector
            label={t("filters.accounts")}
            options={accountOptions}
            multiple
            value={selectedAccountIds.map(String)}
            onChange={setAccountValues}
            selectAll
            selectAllLabel={t("filters.selectAll")}
            clearLabel={t("filters.clearSelection")}
            searchPlaceholder={t("filters.searchAccounts")}
            emptyLabel={t("empty.noAccounts")}
            disabled={!initialized}
          />
          {initialized && accounts.length > 0 && !hasAccountSelection && (
            <div className={styles.accountHint} role="status">
              {t("empty.selectHint")}
            </div>
          )}
        </div>
      </Section>

      <Section
        title={t("sections.filters")}
        description={t("sections.filtersDescription")}
      >
        <FilterBar
          secondary={periodPreset === "custom" ? (
            <FilterItem size="fluid">{periodPicker}</FilterItem>
          ) : undefined}
          actions={hasOverrides ? (
            <Button
              variant="ghost"
              size="sm"
              leadingIcon={<RotateCcw {...iconDefaults} />}
              onClick={restoreProfile}
            >
              {t("actions.restore")}
            </Button>
          ) : undefined}
        >
          <Select
            label={t("filters.profile")}
            value={profileId}
            disabled={!initialized || profiles.length === 0}
            options={profiles.map((profile) => ({
              value: profile.id,
              label: `${profile.name}${profile.is_default ? t("profile.default") : ""}`,
            }))}
            onChange={(event) => chooseProfile(event.target.value)}
            controlSize="sm"
          />
          {periodPreset !== "custom" && periodPicker}
          <Select
            label={t("filters.metric")}
            value={metric}
            options={(Object.keys(METRIC_LABELS) as BillingMetric[]).map((value) => ({
              value,
              label: t(METRIC_LABELS[value]),
            }))}
            onChange={(event) => setMetric(event.target.value as BillingMetric)}
            controlSize="sm"
          />
          <Select
            label={t("filters.granularity")}
            value={granularity}
            options={(Object.keys(GRANULARITY_LABELS) as BillingGranularity[]).map((value) => ({
              value,
              label: t(GRANULARITY_LABELS[value]),
            }))}
            onChange={(event) => setGranularity(event.target.value as BillingGranularity)}
            controlSize="sm"
          />
          <Select
            label={t("filters.groupBy")}
            value={groupBy}
            options={(Object.keys(GROUP_BY_LABELS) as BillingGroupBy[]).map((value) => ({
              value,
              label: t(GROUP_BY_LABELS[value]),
            }))}
            onChange={(event) => setGroupBy(event.target.value as BillingGroupBy)}
            controlSize="sm"
          />
        </FilterBar>

        {periodPreset === "custom" && !period && (
          <Alert
            variant="warning"
            title={t("errors.customTitle")}
            description={t("errors.customDescription")}
          />
        )}

        {selectedProfile && (
          <div className={styles.profileContext}>
            <div>
              <span>{t("profile.applied")}</span>
              <strong>{selectedProfile.name}{selectedProfile.is_default ? t("profile.default") : ""}</strong>
            </div>
            <p>{profileSummary(selectedProfile, metricLabels, granularityLabels, groupLabels, selectedProfile.exclude_record_types.length ? t("filters.excluded", { types: selectedProfile.exclude_record_types.join(", ") }) : t("filters.noExclusionsByType"))}</p>
            {hasOverrides && <Badge variant="warning">{t("profile.temporary")}</Badge>}
          </div>
        )}

        <details className={styles.advancedFilters}>
          <summary>{t("filters.more")}</summary>
          <div className={styles.advancedContent}>
            <div className={styles.advancedHeading}>
              <strong>{t("filters.excludeTypes")}</strong>
              {!sameStringSet(excludeRecordTypes, selectedProfile?.exclude_record_types || []) && (
                <Badge variant="warning">{t("profile.overridden")}</Badge>
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
          <strong>{t("filters.current")}</strong>
          <span>{queryMetadata}</span>
        </div>
      )}

      {!hasAccountSelection ? (
        <Section appearance="card">
          <DataState
            empty
            emptyTitle={t("empty.select")}
            emptyDescription={t("empty.selectDescription")}
          >
            <span />
          </DataState>
        </Section>
      ) : (
        <div className={styles.analysis}>
          <Section
            title={t("sections.summary")}
            description={period && previousPeriod
              ? t("comparison.range", { previous: formatBillingRange(previousPeriod, locale), current: formatBillingRange(period, locale) })
              : t("sections.summaryDescription")}
          >
            {summary.loading ? (
              <div className={styles.metricGrid}>
                <MetricCard label={t("metrics.period")} value={null} loading />
                <MetricCard label={t("metrics.period")} value={null} loading />
                <MetricCard label={t("metrics.period")} value={null} loading />
              </div>
            ) : summary.error ? (
              <Alert variant="danger" title={t("errors.summaryTitle")} description={errorLabel(summary.error)} />
            ) : summary.data?.totals.length ? (
              <div className={styles.metricGrid}>
                {summary.data.totals.map((total) => {
                  const previous = previousSummary.data?.totals.find((item) => item.currency === total.currency);
                  const trend = previous ? variationTrend(total.amount, previous.amount, t("comparison.trend"), locale) : null;
                  const comparisonText = previousSummary.loading
                    ? t("comparison.loading")
                    : previousSummary.error
                      ? t("comparison.unavailable")
                      : previous
                        ? (
                            <>
                              {t("comparison.previous")}
                              <CurrencyDisplay
                                value={numericAmount(previous.amount)}
                                currency={previous.currency}
                                
                                currencyDisplay="code"
                                minimumFractionDigits={2}
                                maximumFractionDigits={2}
                              />
                            </>
                          )
                        : t("comparison.sameCurrency");
                  const variationText = previous ? variationSupportingText(total.amount, previous.amount, t("comparison.newCost"), t("comparison.noVariation")) : null;
                  return (
                    <MetricCard
                      key={total.currency}
                      label={t("metrics.periodCurrency", {currency:total.currency})}
                      value={(
                        <CurrencyDisplay
                          value={numericAmount(total.amount)}
                          currency={total.currency}
                          
                          currencyDisplay="code"
                          minimumFractionDigits={2}
                          maximumFractionDigits={2}
                        />
                      )}
                      trend={trend || undefined}
                      status={(
                        <StatusIndicator
                          status={statusSemantic(total.status)}
                          label={t(billingStatusKey(total.status))}
                        />
                      )}
                      supportingText={variationText || comparisonText}
                    />
                  );
                })}
              </div>
            ) : (
              <EmptyState
                title={t("empty.noCost")}
                description={t("empty.noCostDescription")}
              />
            )}
          </Section>

          <ChartCard
            title={t("sections.costEvolution")}
            description={timeseries.data
              ? `${granularityLabels[timeseries.data.granularity]} · ${groupLabels[timeseries.data.group_by]}`
              : t("sections.costEvolutionDescription")}
            loading={timeseries.loading}
            error={timeseries.error ? errorLabel(timeseries.error) : undefined}
            empty={Boolean(timeseries.data) && timeseries.data!.points.length === 0}
            emptyTitle={t("empty.noSeries")}
            emptyDescription={t("empty.noSeriesDescription")}
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
              title={t("sections.costByService")}
              description={t("sections.serviceDescription")}
              appearance="card"
            >
              <DataState
                loading={serviceBreakdown.loading}
                error={serviceBreakdown.error ? errorLabel(serviceBreakdown.error) : undefined}
                empty={Boolean(serviceBreakdown.data) && serviceBreakdown.data!.items.length === 0}
                emptyTitle={t("empty.noService")}
                emptyDescription={t("empty.noServiceDescription")}
              >
                {serviceBreakdown.data?.items.length
                  ? <BreakdownTable items={serviceBreakdown.data.items} kind="service" />
                  : <span />}
              </DataState>
            </Section>

            {selectedAccountIds.length > 1 && (
              <Section
                title={t("sections.costByAccount")}
                description={t("sections.accountDescription")}
                appearance="card"
              >
                <DataState
                  loading={accountBreakdown.loading}
                  error={accountBreakdown.error ? errorLabel(accountBreakdown.error) : undefined}
                  empty={Boolean(accountBreakdown.data) && accountBreakdown.data!.items.length === 0}
                  emptyTitle={t("empty.noAccount")}
                  emptyDescription={t("empty.noAccountDescription")}
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
        {t("disclaimer")}
      </p>
    </div>
  );
}
