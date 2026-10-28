"use client";

import Link from "next/link";
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

const entryTypeLabels: Record<EntryType, string> = {
  SAVING: "Saving",
  REALLOCATION: "Realocação",
  ADJUSTMENT: "Ajuste",
};

const basisLabels: Record<Periodicity, string> = {
  MONTHLY: "Mensal / run-rate",
  ONE_TIME: "Pontual",
};

const periodOptions = [
  { value: "this_month", label: "Este mês" },
  { value: "previous_month", label: "Mês anterior" },
  { value: "3m", label: "Últimos 3 meses" },
  { value: "6m", label: "Últimos 6 meses" },
  { value: "year", label: "Este ano" },
  { value: "custom", label: "Personalizado" },
];

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

function effectiveDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function createdAt(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
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
      locale="pt-BR"
      minimumFractionDigits={2}
      maximumFractionDigits={8}
    />
  );
}

function flowEntryStatus(entry: FlowEntry): { status: ProductStatus; label: string } {
  if (entry.is_reversed) return { status: "warning", label: "Revertida" };
  if (entry.is_reversal) return { status: "info", label: "Reversal" };
  return { status: "success", label: "Registrada" };
}

function ManualEntryDialog({ accounts, saving, error, onClose, onSubmit }: {
  accounts: CloudAccount[];
  saving: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
}) {
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
    if (!cloudAccountId) return setValidation("Selecione uma conta para a movimentação.");
    if (!normalizedAmount) return setValidation("Informe um valor positivo com até 8 casas decimais.");
    if (!effective || effective > localDateInput()) return setValidation("A data efetiva não pode estar no futuro.");
    if (description.trim().length < 3) return setValidation("Descreva o contexto da movimentação com pelo menos 3 caracteres.");
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
          <DialogTitle>Nova movimentação</DialogTitle>
          <DialogDescription>Registre um fato financeiro no ledger append-only.</DialogDescription>
        </DialogHeader>
        <form className={styles.dialogForm} onSubmit={submit}>
          <Select
            label="Tipo"
            value={entryType}
            disabled={saving}
            options={MANUAL_ENTRY_TYPES.map((type) => ({ value: type, label: entryTypeLabels[type as EntryType] }))}
            onChange={(event) => {
              const next = event.target.value as EntryType;
              setEntryType(next);
              setPeriodicity(next === "SAVING" ? "MONTHLY" : "ONE_TIME");
            }}
          />
          {entryType === "ADJUSTMENT" ? (
            <Select
              label="Direção"
              value={adjustmentDirection}
              disabled={saving}
              options={[{ value: "CREDIT", label: "Crédito" }, { value: "DEBIT", label: "Débito" }]}
              onChange={(event) => setAdjustmentDirection(event.target.value as Direction)}
            />
          ) : (
            <Input label="Direção" value={direction === "CREDIT" ? "Crédito" : "Débito"} readOnly />
          )}
          <Select
            label="Provider"
            value={provider}
            disabled={saving}
            options={Array.from(new Set(accounts.map((account) => account.provider))).map((value) => ({ value, label: providerLabel(value) }))}
            onChange={(event) => changeProvider(event.target.value)}
          />
          <Select
            label="Conta"
            value={cloudAccountId}
            disabled={saving}
            required
            placeholder="Selecione uma conta"
            options={visibleAccounts.map((account) => ({ value: String(account.id), label: accountLabel(account) }))}
            onChange={(event) => setCloudAccountId(event.target.value)}
          />
          <Input
            label="Valor"
            value={amount}
            inputMode="decimal"
            autoComplete="off"
            placeholder="2500.00"
            disabled={saving}
            required
            onChange={(event) => setAmount(event.target.value)}
          />
          <Select
            label="Moeda"
            value={currency}
            disabled={saving}
            options={[{ value: "BRL", label: "BRL — Real brasileiro" }, { value: "USD", label: "USD — Dólar americano" }]}
            onChange={(event) => setCurrency(event.target.value as "BRL" | "USD")}
          />
          <Input
            label="Data da movimentação"
            type="date"
            value={effective}
            max={localDateInput()}
            disabled={saving}
            required
            onChange={(event) => setEffective(event.target.value)}
          />
          {entryType === "SAVING" && (
            <Select
              label="Periodicidade"
              value={periodicity}
              disabled={saving}
              options={[{ value: "MONTHLY", label: "Mensal" }, { value: "ONE_TIME", label: "Pontual" }]}
              onChange={(event) => setPeriodicity(event.target.value as Periodicity)}
            />
          )}
          <Textarea
            label="Descrição"
            value={description}
            rows={4}
            maxLength={2000}
            disabled={saving}
            required
            placeholder="Contexto para auditoria da movimentação"
            onChange={(event) => setDescription(event.target.value)}
          />
          {(validation || error) && <Alert variant="danger" description={validation || error} />}
          <DialogFooter className={styles.dialogActions}>
            <Button variant="secondary" disabled={saving} onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={saving} disabled={!visibleAccounts.length}>Registrar movimentação</Button>
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
  const [reason, setReason] = useState("");
  const [validation, setValidation] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (reason.trim().length < 3) return setValidation("Informe o motivo da reversão.");
    setValidation("");
    await onSubmit(reason.trim());
  }

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Reverter movimentação</DialogTitle>
          <DialogDescription>Uma nova entry oposta será criada; a original permanece no histórico.</DialogDescription>
        </DialogHeader>
        <form className={styles.dialogForm} onSubmit={submit}>
          <p><strong>{entryTypeLabels[entry.logical_entry_type]}</strong> · <Money amount={entry.amount} currency={entry.currency} /></p>
          <Textarea
            label="Motivo da reversão"
            value={reason}
            rows={4}
            maxLength={2000}
            disabled={saving}
            required
            onChange={(event) => setReason(event.target.value)}
          />
          {(validation || error) && <Alert variant="danger" description={validation || error} />}
          <DialogFooter className={styles.dialogActions}>
            <Button variant="secondary" disabled={saving} onClick={onClose}>Cancelar</Button>
            <Button type="submit" loading={saving}>Confirmar reversão</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function FlowChart({ points }: { points: TimeseriesPoint[] }) {
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
      <svg className={styles.chart} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolução temporal de savings, reutilizações e saldo acumulado">
        <line className={styles.chartAxis} x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} />
        {points.map((point, index) => {
          const x = pad + index * step + step * 0.2;
          const savingHeight = (Math.abs(Number(point.recognized_savings)) / max) * innerHeight;
          const reallocHeight = (Math.abs(Number(point.reallocated)) / max) * innerHeight;
          return (
            <g key={`${point.bucket}-${index}`}>
              <rect className={styles.chartSaving} x={x} y={height - pad - savingHeight} width={Math.max(step * 0.22, 3)} height={savingHeight} />
              <rect className={styles.chartReallocated} x={x + step * 0.28} y={height - pad - reallocHeight} width={Math.max(step * 0.22, 3)} height={reallocHeight} />
              <title>{`${point.bucket}: saving ${point.recognized_savings}; reutilização ${point.reallocated}; saldo ${point.cumulative_balance}`}</title>
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
        if (active) setAnalyticsError(error instanceof Error ? error.message : "Não foi possível carregar os indicadores do Fluxo.");
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
        if (active) setTableError(error instanceof Error ? error.message : "Não foi possível carregar as movimentações.");
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
      setSuccess("Movimentação registrada no Fluxo FinOps.");
      setReloadToken((value) => value + 1);
      setPage(1);
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Não foi possível registrar a movimentação.");
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
      setSuccess("Reversão registrada. A movimentação original foi preservada.");
      setReloadToken((value) => value + 1);
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Não foi possível reverter a movimentação.");
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
        title="Fluxo"
        description="Savings reconhecidos, reutilizações e ajustes registrados no ledger. Fluxo não representa custo faturado pela cloud."
        metadata="FinOps Flow · ledger append-only"
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
            Nova movimentação
          </Button>
        )}
      />

      {success && <Alert variant="success" title="Movimentação atualizada" description={success} />}

      <Section title="Contexto e filtros" description="O recorte altera somente as consultas do Flow; nenhuma mudança de tema ou layout dispara mutações.">
        <FilterBar>
          <Select
            label="Período"
            value={period}
            options={periodOptions}
            onChange={(event) => setPeriod(event.target.value as PeriodPreset)}
          />
          <Select
            label="Provider"
            value={provider}
            options={[{ value: "all", label: "Todos" }, ...options.providers.map((value) => ({ value, label: providerLabel(value) }))]}
            onChange={(event) => setProvider(event.target.value)}
          />
          <Select
            label="Conta"
            value={accountId}
            options={[{ value: "all", label: "Todas as contas" }, ...visibleAccounts.map((account) => ({ value: account.native_account_id, label: accountLabel(account) }))]}
            onChange={(event) => setAccountId(event.target.value)}
          />
          <Select
            label="Moeda"
            value={currency}
            options={[{ value: "all", label: "Todas (sem consolidar)" }, ...options.currencies.map((value) => ({ value, label: value }))]}
            onChange={(event) => setCurrency(event.target.value)}
          />
          <Select
            label="Base financeira"
            value={periodicity}
            options={[{ value: "all", label: "Todas (separadas)" }, ...options.periodicities.map((value) => ({ value, label: basisLabels[value as Periodicity] || value }))]}
            onChange={(event) => setPeriodicity(event.target.value)}
          />
          <Select
            label="Origem"
            value={source}
            options={[{ value: "all", label: "Todas" }, ...options.sources.map((value) => ({ value, label: sourceLabel(value) }))]}
            onChange={(event) => setSource(event.target.value)}
          />
        </FilterBar>
        {period === "custom" && (
          <div className={styles.filterDates}>
            <Input label="De" type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} />
            <Input label="Até" type="date" value={customTo} max={localDateInput()} onChange={(event) => setCustomTo(event.target.value)} />
          </div>
        )}
      </Section>

      {analyticsError && (
        <Alert variant="danger" title="Indicadores indisponíveis" description={analyticsError} />
      )}

      <Section title="Resumo financeiro" description="Cada moeda e base financeira permanece separada; nenhum total entre moedas é inventado.">
        <DataState
          loading={loading}
          empty={!loading && !analyticsError && summary.length === 0}
          emptyTitle="Nenhuma movimentação registrada no período"
          emptyDescription="O Flow só apresenta fatos financeiros existentes no ledger."
          emptyAction={<Button leadingIcon={<Plus {...iconDefaults} />} onClick={() => setCreateOpen(true)}>Nova movimentação</Button>}
        >
          <div className={styles.metricGroups}>
            {summary.map((item) => (
              <div className={styles.metricGroup} key={`${item.currency}-${item.basis}`}>
                <h3 className={styles.metricGroupHeading}>{item.currency} · {basisLabels[item.basis]}</h3>
                <div className={styles.metricGrid}>
                  <MetricCard
                    label="Savings reconhecidos"
                    value={<><Money amount={item.recognized_savings} currency={item.currency} />{item.basis === "MONTHLY" ? "/mês" : ""}</>}
                  />
                  <MetricCard
                    label="Reutilizado"
                    value={<><Money amount={item.reallocated} currency={item.currency} />{item.basis === "MONTHLY" ? "/mês" : ""}</>}
                  />
                  <MetricCard
                    label="Ajustes líquidos"
                    value={<><Money amount={item.adjustment_net} currency={item.currency} />{item.basis === "MONTHLY" ? "/mês" : ""}</>}
                  />
                  <MetricCard
                    label={item.basis === "MONTHLY" ? "Saldo líquido de run-rate" : "Saldo FinOps disponível"}
                    value={<><Money amount={item.balance} currency={item.currency} />{item.basis === "MONTHLY" ? "/mês" : ""}</>}
                  />
                </div>
              </div>
            ))}
          </div>
        </DataState>
      </Section>

      <ChartCard
        title="Evolução temporal"
        description="Valores agregados no backend por moeda e base financeira; o saldo acumulado inclui o saldo anterior ao período."
        loading={loading}
        error={analyticsError || undefined}
        empty={!loading && !analyticsError && activeSeries.length === 0}
        emptyTitle="Sem dados para o gráfico"
        emptyDescription="Não há série temporal no recorte selecionado."
        legend={(
          <div className={styles.chartLegend}>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendSaving}`} aria-hidden="true" />Savings</span>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendReallocated}`} aria-hidden="true" />Reutilizações</span>
            <span className={styles.chartLegendItem}><span className={`${styles.legendSwatch} ${styles.legendBalance}`} aria-hidden="true" />Saldo acumulado</span>
          </div>
        )}
        actions={(
          <div className={styles.tableActions}>
            <Select
              label="Moeda do gráfico"
              value={effectiveChartCurrency}
              disabled={currency !== "all"}
              options={options.currencies.map((value) => ({ value, label: value }))}
              onChange={(event) => setChartCurrency(event.target.value)}
            />
            <Select
              label="Base"
              value={effectiveChartBasis}
              disabled={periodicity !== "all"}
              options={options.periodicities.map((value) => ({ value, label: basisLabels[value as Periodicity] || value }))}
              onChange={(event) => setChartBasis(event.target.value as Periodicity)}
            />
          </div>
        )}
      >
        <FlowChart points={activeSeries} />
      </ChartCard>

      <div className={styles.breakdownGrid}>
        <Section appearance="card" title="Savings reconhecidos por conta">
          <DataState
            loading={loading}
            error={analyticsError || undefined}
            empty={!loading && !analyticsError && accountBreakdown.length === 0}
            emptyTitle="Nenhum saving por conta"
            emptyDescription="Nenhum saving reconhecido para este recorte."
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
        <Section appearance="card" title="Savings reconhecidos por origem">
          <DataState
            loading={loading}
            error={analyticsError || undefined}
            empty={!loading && !analyticsError && sourceBreakdown.length === 0}
            emptyTitle="Nenhum saving por origem"
            emptyDescription="Nenhum saving reconhecido para este recorte."
          >
            <div className={styles.breakdownList}>
              {sourceBreakdown.map((item) => (
                <div className={styles.breakdownLine} key={`${item.currency}-${item.basis}-${item.source}`}>
                  <span className={styles.breakdownName}>{sourceLabel(item.source || "")}</span>
                  <strong className={styles.breakdownValue}><Money amount={item.recognized_savings} currency={item.currency} /></strong>
                </div>
              ))}
            </div>
          </DataState>
        </Section>
      </div>

      <Section
        appearance="card"
        title="Movimentações"
        description={`${entries.total} movimentação(ões) no escopo. Reversões permanecem visíveis.`}
        actions={(
          <div className={styles.tableActions}>
            <Select
              label="Tipo"
              value={entryType}
              options={[
                { value: "all", label: "Todos" },
                { value: "SAVING", label: "Saving" },
                { value: "REALLOCATION", label: "Realocação" },
                { value: "ADJUSTMENT", label: "Ajuste" },
              ]}
              onChange={(event) => {
                setEntryType(event.target.value);
                setPage(1);
              }}
            />
            <Input
              label="Busca"
              value={search}
              placeholder="Descrição, recurso ou oportunidade"
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
          error={tableError || undefined}
          empty={!tableLoading && !tableError && entries.items.length === 0}
          emptyTitle="Nenhuma movimentação encontrada"
          emptyDescription="Ajuste os filtros ou registre uma movimentação real no ledger."
        >
          <Table aria-label="Movimentações do Fluxo FinOps">
            <TableHeader>
              <TableRow staticRow>
                <TableHead>Data</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Descrição</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Conta</TableHead>
                <TableHead>Origem</TableHead>
                <TableHead numeric>Valor</TableHead>
                <TableHead>Periodicidade</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.items.map((entry) => {
                const status = flowEntryStatus(entry);
                return (
                  <TableRow key={entry.id}>
                    <TableCell>{effectiveDate(entry.effective_at)}</TableCell>
                    <TableCell>{entryTypeLabels[entry.logical_entry_type]}</TableCell>
                    <TableCell>{entry.description || "—"}</TableCell>
                    <TableCell><ProviderBadge provider={entry.provider} /></TableCell>
                    <TableCell>
                      <span className={styles.movementPrimary}>{entry.account_name || entry.account_id}</span>
                      <span className={styles.movementSecondary}>{entry.account_id}</span>
                    </TableCell>
                    <TableCell>
                      <span className={styles.movementPrimary}>{sourceLabel(entry.logical_source)}</span>
                      {entry.is_reversal && <span className={styles.movementSecondary}>Reversal do ledger</span>}
                    </TableCell>
                    <TableCell numeric>
                      <span className={styles.movementPrimary}>{entry.direction === "CREDIT" ? "+ " : "− "}<Money amount={entry.amount} currency={entry.currency} /></span>
                      <span className={styles.movementSecondary}>{entry.currency}</span>
                    </TableCell>
                    <TableCell>{basisLabels[entry.periodicity]}</TableCell>
                    <TableCell><StatusIndicator status={status.status} label={status.label} /></TableCell>
                    <TableCell>
                      <div className={styles.tableActions}>
                        <Button size="sm" variant="ghost" onClick={() => setDetail(entry)}>Detalhes</Button>
                        {entry.opportunity_id && (
                          <Link className={styles.actionLink} href={`/opportunities?opportunity_id=${encodeURIComponent(entry.opportunity_id)}`}>
                            <ExternalLink {...iconDefaults} /> Ver oportunidade
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
                            Reverter
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
              <DialogTitle>Detalhes da movimentação</DialogTitle>
              <DialogDescription>Registro persistido no ledger FinOps.</DialogDescription>
            </DialogHeader>
            <dl className={styles.detailGrid}>
              <DetailItem label="Tipo">{entryTypeLabels[detail.logical_entry_type]}</DetailItem>
              <DetailItem label="Direção">{detail.direction === "CREDIT" ? "Crédito" : "Débito"}</DetailItem>
              <DetailItem label="Valor"><Money amount={detail.amount} currency={detail.currency} /></DetailItem>
              <DetailItem label="Currency">{detail.currency}</DetailItem>
              <DetailItem label="Provider"><ProviderBadge provider={detail.provider} /></DetailItem>
              <DetailItem label="Conta">{detail.account_name || detail.account_id}</DetailItem>
              <DetailItem label="Data efetiva">{effectiveDate(detail.effective_at)}</DetailItem>
              <DetailItem label="Criado em">{createdAt(detail.created_at)}</DetailItem>
              <DetailItem label="Origem">{sourceLabel(detail.logical_source)}</DetailItem>
              <DetailItem label="Criado por">{detail.created_by_name || detail.created_by || "Sistema"}</DetailItem>
              <DetailItem label="Periodicidade">{basisLabels[detail.periodicity]}</DetailItem>
              <DetailItem label="Status"><StatusIndicator status={flowEntryStatus(detail).status} label={flowEntryStatus(detail).label} /></DetailItem>
              <DetailItem label="Descrição">{detail.description || "—"}</DetailItem>
              {detail.reversal_of_id && <DetailItem label="Original">{detail.reversal_of_id}</DetailItem>}
              {detail.reversed_by_id && <DetailItem label="Reversal">{detail.reversed_by_id}</DetailItem>}
            </dl>
            {detail.opportunity_id && (
              <Section title="Oportunidade associada">
                <div className={styles.detailStack}>
                  <span>{detail.opportunity_title || detail.opportunity_id}</span>
                  <span className={styles.secondaryText}>Service: {detail.opportunity_service || "Não informado"}</span>
                  <span className={styles.secondaryText}>Treatment event: {detail.source_event_id || "—"}</span>
                  <Link className={styles.actionLink} href={`/opportunities?opportunity_id=${encodeURIComponent(detail.opportunity_id)}`}>
                    <ExternalLink {...iconDefaults} /> Ver oportunidade associada
                  </Link>
                </div>
              </Section>
            )}
            <DialogFooter className={styles.detailActions}>
              <Button variant="secondary" onClick={() => setDetail(null)}>Fechar</Button>
              {!detail.is_reversed && !detail.is_reversal && (
                <Button
                  variant="danger"
                  leadingIcon={<RotateCcw {...iconDefaults} />}
                  onClick={() => {
                    setMutationError("");
                    setReverseTarget(detail);
                  }}
                >
                  Reverter
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
