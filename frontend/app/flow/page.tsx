"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { ExternalLink, Plus, RotateCcw } from "lucide-react";
import {
  ChartCard,
  CurrencyDisplay,
  DataState,
  FilterBar,
  MetricCard,
  PageHeader,
  ProviderBadge,
  Section,
  StatusIndicator,
  type ProductStatus,
} from "@/components/aven";
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Pagination,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import { api } from "@/lib/api";
import {
  accountsForProvider,
  defaultCurrencyForProvider,
  directionForEntryType,
  MANUAL_ENTRY_TYPES,
  normalizePositiveDecimal,
  sourceLabel,
} from "@/lib/finops-ledger.mjs";
import type { CloudAccount } from "@/lib/types";
import styles from "./flow-layout.module.css";

type EntryType = "SAVING" | "REALLOCATION" | "ADJUSTMENT";
type Direction = "CREDIT" | "DEBIT";
type Periodicity = "ONE_TIME" | "MONTHLY";
type PeriodPreset = "this_month" | "previous_month" | "3m" | "6m" | "year" | "custom";

type SummaryItem = {
  currency: string;
  basis: Periodicity;
  recognized_savings: string;
  reallocated: string;
  adjustment_net: string;
  balance: string;
};

type TimeseriesPoint = SummaryItem & {
  bucket: string;
  balance_delta: string;
  cumulative_balance: string;
};

type TimeseriesResponse = { granularity: "day" | "month"; items: TimeseriesPoint[] };

type BreakdownItem = {
  currency: string;
  basis: Periodicity;
  account_id?: string;
  account_name?: string | null;
  source?: string;
  recognized_savings: string;
};

type Breakdowns = { by_account: BreakdownItem[]; by_source: BreakdownItem[] };

type FlowOptions = {
  currencies: string[];
  periodicities: string[];
  providers: string[];
  sources: string[];
};

type FlowEntry = {
  id: string;
  entry_type: EntryType;
  direction: Direction;
  provider: string;
  cloud_account_id: number;
  account_id: string;
  account_name: string | null;
  amount: string;
  currency: string;
  effective_at: string;
  source: string;
  source_reference: string | null;
  opportunity_id: string | null;
  source_event_id: string | null;
  description: string | null;
  context: Record<string, unknown>;
  periodicity: Periodicity;
  reference_period_start: string | null;
  reference_period_end: string | null;
  created_by: string | null;
  created_by_name: string | null;
  created_at: string;
  reversal_of_id: string | null;
  is_reversed: boolean;
  reversed_by_id: string | null;
  is_reversal: boolean;
  logical_entry_type: EntryType;
  logical_source: string;
  opportunity_title: string | null;
  opportunity_service: string | null;
  opportunity_resource_id: string | null;
};

type FlowEntryPage = {
  items: FlowEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

const entryTypeLabels = { SAVING: "types.saving", REALLOCATION: "types.reallocation", ADJUSTMENT: "types.adjustment" } as const satisfies Record<EntryType, string>;

const basisLabels = { MONTHLY: "types.monthlyBasis", ONE_TIME: "types.oneTime" } as const satisfies Record<Periodicity, string>;

const periodOptions = [
  { value: "this_month", label: "periods.thisMonth" }, { value: "previous_month", label: "periods.previousMonth" },
  { value: "3m", label: "periods.last3" }, { value: "6m", label: "periods.last6" },
  { value: "year", label: "periods.thisYear" }, { value: "custom", label: "periods.custom" },
] as const;

function localDateInput(date = new Date()): string {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function addMonths(date: Date, months: number) {
  const copy = new Date(date);
  copy.setMonth(copy.getMonth() + months);
  return copy;
}

function periodRange(preset: PeriodPreset, customFrom: string, customTo: string) {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  let from = new Date(year, 0, 1);
  let to = new Date(year + 1, 0, 1);
  if (preset === "this_month") {
    from = new Date(year, month, 1);
    to = new Date(year, month + 1, 1);
  } else if (preset === "previous_month") {
    from = new Date(year, month - 1, 1);
    to = new Date(year, month, 1);
  } else if (preset === "3m" || preset === "6m") {
    from = addMonths(new Date(year, month, 1), preset === "3m" ? -2 : -5);
    to = new Date(year, month + 1, 1);
  } else if (preset === "custom" && customFrom && customTo) {
    from = new Date(`${customFrom}T00:00:00`);
    to = new Date(`${customTo}T00:00:00`);
    to.setDate(to.getDate() + 1);
  }
  return { from: from.toISOString(), to: to.toISOString() };
}

function effectiveDate(value: string, locale: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? new Intl.DateTimeFormat(locale, {year:"numeric",month:"2-digit",day:"2-digit"}).format(new Date(Number(year),Number(month)-1,Number(day))) : value;
}

function createdAt(value: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function providerLabel(provider: string): string {
  return provider.toUpperCase();
}

function accountLabel(account: CloudAccount): string {
  return account.name ? `${account.name} · ${account.native_account_id}` : account.native_account_id;
}

function queryString(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "" && value !== "all") params.set(key, String(value));
  });
  return params.toString();
}

function Money({ amount, currency }: { amount: string | number; currency: string }) {
  const value = Number(amount);
  return (
    <CurrencyDisplay
      value={Number.isFinite(value) ? value : null}
      currency={currency}
      minimumFractionDigits={2}
      maximumFractionDigits={8}
    />
  );
}

function flowEntryStatus(entry: FlowEntry): { status: ProductStatus; labelKey: "status.reversed" | "status.reversal" | "status.recorded" } {
  if (entry.is_reversed) return { status: "warning", labelKey: "status.reversed" };
  if (entry.is_reversal) return { status: "info", labelKey: "status.reversal" };
  return { status: "success", labelKey: "status.recorded" };
}

function ManualEntryDialog({ accounts, saving, error, onClose, onSubmit }: {
  accounts: CloudAccount[];
  saving: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const t = useTranslations("flow");
  const errorLabel = (key: string) => key === "create" ? t("errors.create") : key === "reverse" ? t("errors.reverse") : t("errors.analytics");
  const initialProvider = accounts.find((account) => account.enabled)?.provider || accounts[0]?.provider || "aws";
  const initialAccounts = accountsForProvider(accounts, initialProvider);
  const [entryType, setEntryType] = useState<EntryType>("SAVING");
  const [provider, setProvider] = useState(initialProvider);
  const [cloudAccountId, setCloudAccountId] = useState(String(initialAccounts[0]?.id || ""));
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState<"BRL" | "USD">(defaultCurrencyForProvider(initialProvider, "USD"));
  const [effective, setEffective] = useState(localDateInput());
  const [periodicity, setPeriodicity] = useState<Periodicity>("MONTHLY");
  const [adjustmentDirection, setAdjustmentDirection] = useState<Direction>("CREDIT");
  const [description, setDescription] = useState("");
  const [validation, setValidation] = useState("");
  const requestId = useRef("");
  const visibleAccounts = useMemo(() => accountsForProvider(accounts, provider), [accounts, provider]);
  const direction = directionForEntryType(entryType, adjustmentDirection) as Direction;

  function changeProvider(nextProvider: string) {
    const nextAccounts = accountsForProvider(accounts, nextProvider);
    setProvider(nextProvider);
    setCloudAccountId(String(nextAccounts[0]?.id || ""));
    setCurrency(defaultCurrencyForProvider(nextProvider, currency));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    const normalizedAmount = normalizePositiveDecimal(amount);
    if (!cloudAccountId) return setValidation("validation.account");
    if (!normalizedAmount) return setValidation("validation.amount");
    if (!effective || effective > localDateInput()) return setValidation("validation.date");
    if (description.trim().length < 3) return setValidation("validation.description");
    if (!requestId.current) requestId.current = crypto.randomUUID();
    await onSubmit({
      entry_type: entryType,
      direction,
      provider,
      cloud_account_id: Number(cloudAccountId),
      amount: normalizedAmount,
      currency,
      effective_date: effective,
      periodicity: entryType === "SAVING" ? periodicity : "ONE_TIME",
      description: description.trim(),
      manual_entry_request_id: requestId.current,
    });
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("actions.new")}</DialogTitle>
          <DialogDescription>{t("forms.newDescription")}</DialogDescription>
        </DialogHeader>
        <form className={styles.dialogForm} onSubmit={submit}>
          <Select
            label={t("forms.type")}
            value={entryType}
            disabled={saving}
            options={MANUAL_ENTRY_TYPES.map((type) => ({ value: type, label: t(entryTypeLabels[type as EntryType]) }))}
            onChange={(event) => {
              const next = event.target.value as EntryType;
              setEntryType(next);
              setPeriodicity(next === "SAVING" ? "MONTHLY" : "ONE_TIME");
            }}
          />
          {entryType === "ADJUSTMENT" ? (
            <Select
              label={t("forms.direction")}
              value={adjustmentDirection}
              disabled={saving}
              options={[{ value: "CREDIT", label: t("types.credit") }, { value: "DEBIT", label: t("types.debit") }]}
              onChange={(event) => setAdjustmentDirection(event.target.value as Direction)}
            />
          ) : (
            <Input label={t("forms.direction")} value={direction === "CREDIT" ? t("types.credit") : t("types.debit")} readOnly />
          )}
          <Select
            label={t("forms.provider")}
            value={provider}
            disabled={saving}
            options={Array.from(new Set(accounts.map((account) => account.provider))).map((value) => ({ value, label: providerLabel(value) }))}
            onChange={(event) => changeProvider(event.target.value)}
          />
          <Select
            label={t("forms.account")}
            value={cloudAccountId}
            disabled={saving}
            required
            placeholder={t("forms.selectAccount")}
            options={visibleAccounts.map((account) => ({ value: String(account.id), label: accountLabel(account) }))}
            onChange={(event) => setCloudAccountId(event.target.value)}
          />
          <Input
            label={t("forms.amount")}
            value={amount}
            inputMode="decimal"
            autoComplete="off"
            placeholder="2500.00"
            disabled={saving}
            required
            onChange={(event) => setAmount(event.target.value)}
          />
          <Select
            label={t("forms.currency")}
            value={currency}
            disabled={saving}
            options={[{ value: "BRL", label: t("forms.brl") }, { value: "USD", label: t("forms.usd") }]}
            onChange={(event) => setCurrency(event.target.value as "BRL" | "USD")}
          />
          <Input
            label={t("forms.effectiveDate")}
            type="date"
            value={effective}
            max={localDateInput()}
            disabled={saving}
            required
            onChange={(event) => setEffective(event.target.value)}
          />
          {entryType === "SAVING" && (
            <Select
              label={t("forms.periodicity")}
              value={periodicity}
              disabled={saving}
              options={[{ value: "MONTHLY", label: t("types.monthly") }, { value: "ONE_TIME", label: t("types.oneTime") }]}
              onChange={(event) => setPeriodicity(event.target.value as Periodicity)}
            />
          )}
          <Textarea
            label={t("forms.description")}
            value={description}
            rows={4}
            maxLength={2000}
            disabled={saving}
            required
            placeholder={t("forms.descriptionPlaceholder")}
            onChange={(event) => setDescription(event.target.value)}
          />
          {(validation || error) && <Alert variant="danger" description={validation ? t(validation as Parameters<typeof t>[0]) : errorLabel(error)} />}
          <DialogFooter className={styles.dialogActions}>
            <Button variant="secondary" disabled={saving} onClick={onClose}>{t("actions.cancel")}</Button>
            <Button type="submit" loading={saving} disabled={!visibleAccounts.length}>{t("actions.submit")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ReversalDialog({ entry, saving, error, onClose, onSubmit }: {
  entry: FlowEntry;
  saving: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const t = useTranslations("flow");
  const errorLabel = (key: string) => key === "create" ? t("errors.create") : key === "reverse" ? t("errors.reverse") : t("errors.analytics");
  const [reason, setReason] = useState("");
  const [validation, setValidation] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim().length < 3) return setValidation("validation.reason");
    setValidation("");
    await onSubmit(reason.trim());
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("forms.reverseTitle")}</DialogTitle>
          <DialogDescription>{t("forms.reverseDescription")}</DialogDescription>
        </DialogHeader>
        <form className={styles.dialogForm} onSubmit={submit}>
          <p><strong>{t(entryTypeLabels[entry.logical_entry_type])}</strong> · <Money amount={entry.amount} currency={entry.currency} /></p>
          <Textarea
            label={t("forms.reverseReason")}
            value={reason}
            rows={4}
            maxLength={2000}
            disabled={saving}
            required
            onChange={(event) => setReason(event.target.value)}
          />
          {(validation || error) && <Alert variant="danger" description={validation ? t(validation as Parameters<typeof t>[0]) : errorLabel(error)} />}
          <DialogFooter className={styles.dialogActions}>
            <Button variant="secondary" disabled={saving} onClick={onClose}>{t("actions.cancel")}</Button>
            <Button type="submit" loading={saving}>{t("actions.confirmReverse")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FlowChart({ points }: { points: TimeseriesPoint[] }) {
  const t = useTranslations("flow");
  const width = 760;
  const height = 260;
  const pad = 34;
  const values = points.flatMap((point) => [
    Math.abs(Number(point.recognized_savings)),
    Math.abs(Number(point.reallocated)),
    Math.abs(Number(point.cumulative_balance)),
  ]);
  const max = Math.max(...values, 1);
  const innerHeight = height - pad * 2;
  const step = (width - pad * 2) / Math.max(points.length, 1);
  const y = (value: number) => height - pad - (Math.max(value, 0) / max) * innerHeight;
  const line = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${pad + index * step + step / 2} ${y(Number(point.cumulative_balance))}`)
    .join(" ");

  return (
    <div className={styles.chartScroll}>
      <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={t("charts.aria")}>
        <line className={styles.chartAxis} x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
        {points.map((point, index) => {
          const x = pad + index * step + step * 0.2;
          const savingHeight = (Math.abs(Number(point.recognized_savings)) / max) * innerHeight;
          const reallocHeight = (Math.abs(Number(point.reallocated)) / max) * innerHeight;
          return (
            <g key={`${point.bucket}-${index}`}>
              <rect className={styles.chartSaving} x={x} y={height - pad - savingHeight} width={Math.max(step * 0.22, 3)} height={savingHeight} />
              <rect className={styles.chartReallocated} x={x + step * 0.28} y={height - pad - reallocHeight} width={Math.max(step * 0.22, 3)} height={reallocHeight} />
              <title>{t("charts.bucketTitle", {bucket:point.bucket,saving:point.recognized_savings,reallocation:point.reallocated,balance:point.cumulative_balance})}</title>
            </g>
          );
        })}
        <path className={styles.chartBalance} d={line} strokeWidth="2" />
      </svg>
    </div>
  );
}

function DetailItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.detailItem}>
      <dt className={styles.detailLabel}>{label}</dt>
      <dd className={styles.detailValue}>{children}</dd>
    </div>
  );
}

export default function FlowPage() {
  const t = useTranslations("flow");
  const locale = useLocale();
  const sourceName = (value: string) => value === "OPPORTUNITY" ? t("source.opportunity") : value === "MANUAL" ? t("source.manual") : value === "SYSTEM" ? t("source.system") : sourceLabel(value);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [options, setOptions] = useState<FlowOptions>({ currencies: [], periodicities: [], providers: [], sources: [] });
  const [summary, setSummary] = useState<SummaryItem[]>([]);
  const [series, setSeries] = useState<TimeseriesResponse>({ granularity: "month", items: [] });
  const [breakdowns, setBreakdowns] = useState<Breakdowns>({ by_account: [], by_source: [] });
  const [entries, setEntries] = useState<FlowEntryPage>({ items: [], page: 1, page_size: 50, total: 0, total_pages: 0 });
  const [period, setPeriod] = useState<PeriodPreset>("year");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState(localDateInput());
  const [provider, setProvider] = useState("all");
  const [accountId, setAccountId] = useState("all");
  const [currency, setCurrency] = useState("all");
  const [source, setSource] = useState("all");
  const [periodicity, setPeriodicity] = useState("all");
  const [entryType, setEntryType] = useState("all");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [chartCurrency, setChartCurrency] = useState("");
  const [chartBasis, setChartBasis] = useState<Periodicity | "">("");
  const [loading, setLoading] = useState(true);
  const [tableLoading, setTableLoading] = useState(true);
  const [analyticsError, setAnalyticsError] = useState("");
  const [tableError, setTableError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [success, setSuccess] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [reverseTarget, setReverseTarget] = useState<FlowEntry | null>(null);
  const [reversing, setReversing] = useState(false);
  const [detail, setDetail] = useState<FlowEntry | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const range = useMemo(() => periodRange(period, customFrom, customTo), [period, customFrom, customTo]);

  const visibleAccounts = useMemo(
    () => provider === "all" ? accounts : accountsForProvider(accounts, provider),
    [accounts, provider],
  );
  const globalQuery = useMemo(() => ({
    provider: provider === "all" ? undefined : provider,
    account_id: accountId === "all" ? undefined : accountId,
    currency: currency === "all" ? undefined : currency,
    source: source === "all" ? undefined : source,
    periodicity: periodicity === "all" ? undefined : periodicity,
    effective_from: range.from,
    effective_to: range.to,
  }), [provider, accountId, currency, source, periodicity, range]);

  useEffect(() => {
    setPage(1);
    if (accountId !== "all" && !visibleAccounts.some((account) => account.native_account_id === accountId)) setAccountId("all");
  }, [provider, accountId, visibleAccounts]);

  useEffect(() => {
    let active = true;
    api<CloudAccount[]>("/cloud-accounts")
      .then((items) => { if (active) setAccounts(items); })
      .catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const optionQuery = queryString({
      provider: globalQuery.provider,
      account_id: globalQuery.account_id,
      effective_from: range.from,
      effective_to: range.to,
    });
    api<FlowOptions>(`/finops/flow/options?${optionQuery}`)
      .then((value) => {
        if (!active) return;
        setOptions(value);
        if (!chartCurrency || !value.currencies.includes(chartCurrency)) setChartCurrency(value.currencies[0] || "");
        const bases = value.periodicities as Periodicity[];
        if (!chartBasis || !bases.includes(chartBasis)) setChartBasis(bases[0] || "");
      })
      .catch(() => undefined);
    return () => { active = false; };
  }, [globalQuery.provider, globalQuery.account_id, range.from, range.to, reloadToken, chartCurrency, chartBasis]);

  const effectiveChartCurrency = currency === "all" ? chartCurrency : currency;
  const effectiveChartBasis = periodicity === "all" ? chartBasis : (periodicity as Periodicity);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setAnalyticsError("");
    const base = queryString(globalQuery);
    const chart = queryString({
      ...globalQuery,
      currency: effectiveChartCurrency || undefined,
      periodicity: effectiveChartBasis || undefined,
    });
    Promise.all([
      api<SummaryItem[]>(`/finops/flow/summary?${base}`),
      effectiveChartCurrency && effectiveChartBasis
        ? api<TimeseriesResponse>(`/finops/flow/timeseries?${chart}`)
        : Promise.resolve({ granularity: "month" as const, items: [] }),
      api<Breakdowns>(`/finops/flow/breakdowns?${base}`),
    ])
      .then(([nextSummary, nextSeries, nextBreakdowns]) => {
        if (!active) return;
        setSummary(nextSummary);
        setSeries(nextSeries);
        setBreakdowns(nextBreakdowns);
      })
      .catch((error) => {
        if (active) setAnalyticsError("analytics");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [globalQuery, effectiveChartCurrency, effectiveChartBasis, reloadToken]);

  useEffect(() => {
    let active = true;
    setTableLoading(true);
    setTableError("");
    const tableQuery = queryString({
      ...globalQuery,
      entry_type: entryType === "all" ? undefined : entryType,
      search: search.trim() || undefined,
      page,
      page_size: 50,
    });
    api<FlowEntryPage>(`/finops/flow/entries?${tableQuery}`)
      .then((value) => { if (active) setEntries(value); })
      .catch((error) => {
        if (active) setTableError("entries");
      })
      .finally(() => { if (active) setTableLoading(false); });
    return () => { active = false; };
  }, [globalQuery, entryType, search, page, reloadToken]);

  async function createEntry(payload: Record<string, unknown>) {
    setCreating(true);
    setMutationError("");
    setSuccess("");
    try {
      await api<FlowEntry>("/finops/ledger/manual", { method: "POST", body: JSON.stringify(payload) });
      setCreateOpen(false);
      setSuccess("created");
      setReloadToken((value) => value + 1);
      setPage(1);
    } catch (error) {
      setMutationError("create");
    } finally {
      setCreating(false);
    }
  }

  async function reverseEntry(reason: string) {
    if (!reverseTarget) return;
    setReversing(true);
    setMutationError("");
    setSuccess("");
    try {
      await api<FlowEntry>(`/finops/ledger/${reverseTarget.id}/reverse`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setReverseTarget(null);
      setDetail(null);
      setSuccess("reversed");
      setReloadToken((value) => value + 1);
    } catch (error) {
      setMutationError("reverse");
    } finally {
      setReversing(false);
    }
  }

  const activeSeries = series.items.filter(
    (item) => item.currency === effectiveChartCurrency && item.basis === effectiveChartBasis,
  );
  const accountBreakdown = breakdowns.by_account.filter(
    (item) =>
      (!effectiveChartCurrency || item.currency === effectiveChartCurrency) &&
      (!effectiveChartBasis || item.basis === effectiveChartBasis),
  );
  const sourceBreakdown = breakdowns.by_source.filter(
    (item) =>
      (!effectiveChartCurrency || item.currency === effectiveChartCurrency) &&
      (!effectiveChartBasis || item.basis === effectiveChartBasis),
  );
  const maxAccountSaving = Math.max(...accountBreakdown.map((item) => Math.abs(Number(item.recognized_savings))), 1);

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        metadata={t("metadata")}
        actions={(
          <Button
            disabled={!accounts.length}
            leadingIcon={<Plus {...iconDefaults} />}
            onClick={() => {
              setMutationError("");
              setSuccess("");
              setCreateOpen(true);
            }}
          >
            {t("actions.new")}
          </Button>
        )}
      />

      {success && <Alert variant="success" title={t("success.title")} description={success === "created" ? t("success.created") : t("success.reversed")} />}

      <Section title={t("filters.title")} description={t("filters.description")}>
        <FilterBar>
          <Select
            label={t("filters.period")}
            value={period}
            options={periodOptions.map((item) => ({ value: item.value, label: t(item.label) }))}
            onChange={(event) => setPeriod(event.target.value as PeriodPreset)}
          />
          <Select
            label={t("forms.provider")}
            value={provider}
            options={[{ value: "all", label: t("filters.all") }, ...options.providers.map((value) => ({ value, label: providerLabel(value) }))]}
            onChange={(event) => setProvider(event.target.value)}
          />
          <Select
            label={t("forms.account")}
            value={accountId}
            options={[{ value: "all", label: t("filters.allAccounts") }, ...visibleAccounts.map((account) => ({ value: account.native_account_id, label: accountLabel(account) }))]}
            onChange={(event) => setAccountId(event.target.value)}
          />
          <Select
            label={t("forms.currency")}
            value={currency}
            options={[{ value: "all", label: t("filters.allCurrencies") }, ...options.currencies.map((value) => ({ value, label: value }))]}
            onChange={(event) => setCurrency(event.target.value)}
          />
          <Select
            label={t("filters.financialBasis")}
            value={periodicity}
            options={[{ value: "all", label: t("filters.allBases") }, ...options.periodicities.map((value) => ({ value, label: t(basisLabels[value as Periodicity]) || value }))]}
            onChange={(event) => setPeriodicity(event.target.value)}
          />
          <Select
            label={t("filters.origin")}
            value={source}
            options={[{ value: "all", label: "Todas" }, ...options.sources.map((value) => ({ value, label: sourceName(value) }))]}
            onChange={(event) => setSource(event.target.value)}
          />
        </FilterBar>
        {period === "custom" && (
          <div className={styles.filterDates}>
            <Input label={t("filters.from")} type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} />
            <Input label={t("filters.to")} type="date" value={customTo} max={localDateInput()} onChange={(event) => setCustomTo(event.target.value)} />
          </div>
        )}
      </Section>

      {analyticsError && (
        <Alert variant="danger" title={t("errors.analyticsTitle")} description={t("errors.analytics")} />
      )}

      <Section title={t("sections.summary")} description={t("sections.summaryDescription")}>
        <DataState
          loading={loading}
          empty={!loading && !analyticsError && summary.length === 0}
          emptyTitle={t("empty.summary")}
          emptyDescription={t("empty.summaryDescription")}
          emptyAction={<Button leadingIcon={<Plus {...iconDefaults} />} onClick={() => setCreateOpen(true)}>{t("actions.new")}</Button>}
        >
          <div className={styles.metricGroups}>
            {summary.map((item) => (
              <div className={styles.metricGroup} key={`${item.currency}-${item.basis}`}>
                <h3 className={styles.metricGroupHeading}>{item.currency} · {t(basisLabels[item.basis])}</h3>
                <div className={styles.metricGrid}>
                  <MetricCard
                    label={t("metrics.savings")}
                    value={<><Money amount={item.recognized_savings} currency={item.currency} />{item.basis === "MONTHLY" ? t("metrics.monthSuffix") : ""}</>}
                  />
                  <MetricCard
                    label={t("metrics.reallocated")}
                    value={<><Money amount={item.reallocated} currency={item.currency} />{item.basis === "MONTHLY" ? t("metrics.monthSuffix") : ""}</>}
                  />
                  <MetricCard
                    label={t("metrics.adjustments")}
                    value={<><Money amount={item.adjustment_net} currency={item.currency} />{item.basis === "MONTHLY" ? t("metrics.monthSuffix") : ""}</>}
                  />
                  <MetricCard
                    label={item.basis === "MONTHLY" ? t("metrics.runRateBalance") : t("metrics.balance")}
                    value={<><Money amount={item.balance} currency={item.currency} />{item.basis === "MONTHLY" ? t("metrics.monthSuffix") : ""}</>}
                  />
                </div>
              </div>
            ))}
          </div>
        </DataState>
      </Section>

      <ChartCard
        title={t("sections.evolution")}
        description={t("sections.evolutionDescription")}
        loading={loading}
        error={analyticsError ? t("errors.analytics") : undefined}
        empty={!loading && !analyticsError && activeSeries.length === 0}
        emptyTitle={t("empty.chart")}
        emptyDescription={t("empty.chartDescription")}
        legend={(
          <div className={styles.chartLegend}>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendSaving}`} aria-hidden="true" />{t("charts.savings")}</span>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendReallocated}`} aria-hidden="true" />{t("charts.reallocations")}</span>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendBalance}`} aria-hidden="true" />{t("charts.balance")}</span>
          </div>
        )}
        actions={(
          <div className={styles.tableActions}>
            <Select
              label={t("filters.chartCurrency")}
              value={effectiveChartCurrency}
              disabled={currency !== "all"}
              options={options.currencies.map((value) => ({ value, label: value }))}
              onChange={(event) => setChartCurrency(event.target.value)}
            />
            <Select
              label={t("filters.basis")}
              value={effectiveChartBasis}
              disabled={periodicity !== "all"}
              options={options.periodicities.map((value) => ({ value, label: t(basisLabels[value as Periodicity]) || value }))}
              onChange={(event) => setChartBasis(event.target.value as Periodicity)}
            />
          </div>
        )}
      >
        <FlowChart points={activeSeries} />
      </ChartCard>

      <div className={styles.breakdownGrid}>
        <Section appearance="card" title={t("sections.byAccount")}>
          <DataState
            loading={loading}
            error={analyticsError || undefined}
            empty={!loading && !analyticsError && accountBreakdown.length === 0}
            emptyTitle={t("empty.byAccount")}
            emptyDescription={t("empty.byDescription")}
          >
            <div className={styles.breakdownList}>
              {accountBreakdown.map((item) => {
                const width = Math.min(100, Math.abs(Number(item.recognized_savings)) / maxAccountSaving * 100);
                return (
                  <div className={styles.breakdownRow} key={`${item.currency}-${item.basis}-${item.account_id}`}>
                    <div className={styles.breakdownLine}>
                      <span className={styles.breakdownName}>{item.account_name || item.account_id}</span>
                      <strong className={styles.breakdownValue}><Money amount={item.recognized_savings} currency={item.currency} /></strong>
                    </div>
                    <div className={styles.breakdownTrack} aria-hidden="true">
                      <div className={styles.breakdownFill} style={{ width: `${width}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </DataState>
        </Section>
        <Section appearance="card" title={t("sections.bySource")}>
          <DataState
            loading={loading}
            error={analyticsError || undefined}
            empty={!loading && !analyticsError && sourceBreakdown.length === 0}
            emptyTitle={t("empty.bySource")}
            emptyDescription={t("empty.byDescription")}
          >
            <div className={styles.breakdownList}>
              {sourceBreakdown.map((item) => (
                <div className={styles.breakdownLine} key={`${item.currency}-${item.basis}-${item.source}`}>
                  <span className={styles.breakdownName}>{sourceName(item.source || "")}</span>
                  <strong className={styles.breakdownValue}><Money amount={item.recognized_savings} currency={item.currency} /></strong>
                </div>
              ))}
            </div>
          </DataState>
        </Section>
      </div>

      <Section
        appearance="card"
        title={t("sections.entries")}
        description={t("sections.entryCount", {count:entries.total})}
        actions={(
          <div className={styles.tableActions}>
            <Select
              label={t("forms.type")}
              value={entryType}
              options={[
                { value: "all", label: t("filters.all") },
                { value: "SAVING", label: t("types.saving") },
                { value: "REALLOCATION", label: t("types.reallocation") },
                { value: "ADJUSTMENT", label: t("types.adjustment") },
              ]}
              onChange={(event) => {
                setEntryType(event.target.value);
                setPage(1);
              }}
            />
            <Input
              label={t("filters.search")}
              value={search}
              placeholder={t("filters.searchPlaceholder")}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
        )}
      >
        <DataState
          loading={tableLoading}
          error={tableError ? t("errors.entries") : undefined}
          empty={!tableLoading && !tableError && entries.items.length === 0}
          emptyTitle={t("empty.entries")}
          emptyDescription={t("empty.entriesDescription")}
        >
          <Table aria-label={t("table.aria")}>
            <TableHeader>
              <TableRow staticRow>
                <TableHead>{t("headers.date")}</TableHead>
                <TableHead>{t("forms.type")}</TableHead>
                <TableHead>{t("forms.description")}</TableHead>
                <TableHead>{t("forms.provider")}</TableHead>
                <TableHead>{t("forms.account")}</TableHead>
                <TableHead>{t("filters.origin")}</TableHead>
                <TableHead numeric>{t("forms.amount")}</TableHead>
                <TableHead>{t("forms.periodicity")}</TableHead>
                <TableHead>{t("headers.status")}</TableHead>
                <TableHead>{t("headers.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.items.map((entry) => {
                const status = flowEntryStatus(entry);
                return (
                  <TableRow key={entry.id}>
                    <TableCell>{effectiveDate(entry.effective_at, locale)}</TableCell>
                    <TableCell>{t(entryTypeLabels[entry.logical_entry_type])}</TableCell>
                    <TableCell>{entry.description || "—"}</TableCell>
                    <TableCell><ProviderBadge provider={entry.provider} /></TableCell>
                    <TableCell>
                      <span className={styles.movementPrimary}>{entry.account_name || entry.account_id}</span>
                      <span className={styles.movementSecondary}>{entry.account_id}</span>
                    </TableCell>
                    <TableCell>
                      <span className={styles.movementPrimary}>{sourceName(entry.logical_source)}</span>
                      {entry.is_reversal && <span className={styles.movementSecondary}>{t("table.reversal")}</span>}
                    </TableCell>
                    <TableCell numeric>
                      <span className={styles.movementPrimary}>{entry.direction === "CREDIT" ? "+ " : "− "}<Money amount={entry.amount} currency={entry.currency} /></span>
                      <span className={styles.movementSecondary}>{entry.currency}</span>
                    </TableCell>
                    <TableCell>{t(basisLabels[entry.periodicity])}</TableCell>
                    <TableCell><StatusIndicator status={status.status} label={t(status.labelKey)} /></TableCell>
                    <TableCell>
                      <div className={styles.tableActions}>
                        <Button size="sm" variant="ghost" onClick={() => setDetail(entry)}>{t("actions.details")}</Button>
                        {entry.opportunity_id && (
                          <Link className={styles.actionLink} href={`/opportunities?opportunity_id=${encodeURIComponent(entry.opportunity_id)}`}>
                            <ExternalLink {...iconDefaults} /> {t("actions.viewOpportunity")}
                          </Link>
                        )}
                        {!entry.is_reversed && !entry.is_reversal && (
                          <Button
                            size="sm"
                            variant="ghost"
                            leadingIcon={<RotateCcw {...iconDefaults} />}
                            onClick={() => {
                              setMutationError("");
                              setReverseTarget(entry);
                            }}
                          >
                            {t("actions.reverse")}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {entries.total_pages > 1 && (
            <Pagination page={page} pageCount={entries.total_pages} onPageChange={setPage} />
          )}
        </DataState>
      </Section>

      {detail && (
        <Dialog open onOpenChange={(open) => { if (!open) setDetail(null); }}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t("details.title")}</DialogTitle>
              <DialogDescription>{t("details.description")}</DialogDescription>
            </DialogHeader>
            <dl className={styles.detailGrid}>
              <DetailItem label={t("forms.type")}>{t(entryTypeLabels[detail.logical_entry_type])}</DetailItem>
              <DetailItem label={t("forms.direction")}>{detail.direction === "CREDIT" ? t("types.credit") : t("types.debit")}</DetailItem>
              <DetailItem label={t("forms.amount")}><Money amount={detail.amount} currency={detail.currency} /></DetailItem>
              <DetailItem label="Currency">{detail.currency}</DetailItem>
              <DetailItem label={t("forms.provider")}><ProviderBadge provider={detail.provider} /></DetailItem>
              <DetailItem label={t("forms.account")}>{detail.account_name || detail.account_id}</DetailItem>
              <DetailItem label={t("headers.effective")}>{effectiveDate(detail.effective_at, locale)}</DetailItem>
              <DetailItem label={t("headers.createdAt")}>{createdAt(detail.created_at, locale)}</DetailItem>
              <DetailItem label={t("filters.origin")}>{sourceName(detail.logical_source)}</DetailItem>
              <DetailItem label={t("headers.createdBy")}>{detail.created_by_name || detail.created_by || t("source.system")}</DetailItem>
              <DetailItem label={t("forms.periodicity")}>{t(basisLabels[detail.periodicity])}</DetailItem>
              <DetailItem label={t("headers.status")}><StatusIndicator status={flowEntryStatus(detail).status} label={t(flowEntryStatus(detail).labelKey)} /></DetailItem>
              <DetailItem label={t("forms.description")}>{detail.description || "—"}</DetailItem>
              {detail.reversal_of_id && <DetailItem label={t("headers.original")}>{detail.reversal_of_id}</DetailItem>}
              {detail.reversed_by_id && <DetailItem label={t("status.reversal")}>{detail.reversed_by_id}</DetailItem>}
            </dl>
            {detail.opportunity_id && (
              <Section title={t("details.associated")}>
                <div className={styles.detailStack}>
                  <span>{detail.opportunity_title || detail.opportunity_id}</span>
                  <span className={styles.secondaryText}>{t("details.service", {service:detail.opportunity_service || t("details.notInformed")})}</span>
                  <span className={styles.secondaryText}>{t("details.treatment", {event:detail.source_event_id || "—"})}</span>
                  <Link className={styles.actionLink} href={`/opportunities?opportunity_id=${encodeURIComponent(detail.opportunity_id)}`}>
                    <ExternalLink {...iconDefaults} /> {t("actions.viewRelated")}
                  </Link>
                </div>
              </Section>
            )}
            <DialogFooter className={styles.detailActions}>
              <Button variant="secondary" onClick={() => setDetail(null)}>{t("actions.close")}</Button>
              {!detail.is_reversed && !detail.is_reversal && (
                <Button
                  variant="danger"
                  leadingIcon={<RotateCcw {...iconDefaults} />}
                  onClick={() => {
                    setMutationError("");
                    setReverseTarget(detail);
                  }}
                >
                  {t("actions.reverse")}
                </Button>
              )}
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {createOpen && (
        <ManualEntryDialog
          accounts={accounts}
          saving={creating}
          error={mutationError}
          onClose={() => !creating && setCreateOpen(false)}
          onSubmit={createEntry}
        />
      )}
      {reverseTarget && (
        <ReversalDialog
          entry={reverseTarget}
          saving={reversing}
          error={mutationError}
          onClose={() => !reversing && setReverseTarget(null)}
          onSubmit={reverseEntry}
        />
      )}
    </div>
  );
}
