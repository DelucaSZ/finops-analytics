"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { ExternalLink, Plus, RotateCcw, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import {
  accountsForProvider,
  defaultCurrencyForProvider,
  directionForEntryType,
  formatLedgerMoney,
  MANUAL_ENTRY_TYPES,
  normalizePositiveDecimal,
  sourceLabel,
} from "@/lib/finops-ledger.mjs";
import type { CloudAccount } from "@/lib/types";

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
    <div className="dialog-backdrop" role="presentation">
      <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="flow-create-title">
        <div className="dialog-heading">
          <div><span className="eyebrow">FLUXO FINOPS</span><h2 id="flow-create-title">Nova movimentação</h2><p>Registre um fato financeiro no ledger append-only.</p></div>
          <button className="icon-button" type="button" aria-label="Fechar" disabled={saving} onClick={onClose}><X size={18} /></button>
        </div>
        <form onSubmit={submit}>
          <label className="dialog-field">Tipo<select value={entryType} disabled={saving} onChange={(event) => {
            const next = event.target.value as EntryType;
            setEntryType(next);
            setPeriodicity(next === "SAVING" ? "MONTHLY" : "ONE_TIME");
          }}>{MANUAL_ENTRY_TYPES.map((type) => <option key={type} value={type}>{entryTypeLabels[type as EntryType]}</option>)}</select></label>
          <label className="dialog-field">Direção{entryType === "ADJUSTMENT" ? <select value={adjustmentDirection} disabled={saving} onChange={(event) => setAdjustmentDirection(event.target.value as Direction)}><option value="CREDIT">Crédito</option><option value="DEBIT">Débito</option></select> : <input value={direction === "CREDIT" ? "Crédito" : "Débito"} readOnly />}</label>
          <label className="dialog-field">Provider<select value={provider} disabled={saving} onChange={(event) => changeProvider(event.target.value)}>{Array.from(new Set(accounts.map((account) => account.provider))).map((value) => <option key={value} value={value}>{providerLabel(value)}</option>)}</select></label>
          <label className="dialog-field">Conta<select value={cloudAccountId} disabled={saving} required onChange={(event) => setCloudAccountId(event.target.value)}><option value="">Selecione uma conta</option>{visibleAccounts.map((account) => <option key={account.id} value={account.id}>{accountLabel(account)}</option>)}</select></label>
          <label className="dialog-field">Valor<input value={amount} inputMode="decimal" autoComplete="off" placeholder="2500.00" disabled={saving} required onChange={(event) => setAmount(event.target.value)} /></label>
          <label className="dialog-field">Moeda<select value={currency} disabled={saving} onChange={(event) => setCurrency(event.target.value as "BRL" | "USD")}><option value="BRL">BRL — Real brasileiro</option><option value="USD">USD — Dólar americano</option></select></label>
          <label className="dialog-field">Data da movimentação<input type="date" value={effective} max={localDateInput()} disabled={saving} required onChange={(event) => setEffective(event.target.value)} /></label>
          {entryType === "SAVING" && <label className="dialog-field">Periodicidade<select value={periodicity} disabled={saving} onChange={(event) => setPeriodicity(event.target.value as Periodicity)}><option value="MONTHLY">Mensal</option><option value="ONE_TIME">Pontual</option></select></label>}
          <label className="dialog-field">Descrição<textarea value={description} rows={4} maxLength={2000} disabled={saving} required placeholder="Contexto para auditoria da movimentação" onChange={(event) => setDescription(event.target.value)} /></label>
          {(validation || error) && <p className="dialog-error" role="alert">{validation || error}</p>}
          <div className="dialog-actions"><button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button><button className="button primary" type="submit" disabled={saving || !visibleAccounts.length}>{saving ? "Salvando…" : "Registrar movimentação"}</button></div>
        </form>
      </section>
    </div>
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
  return <div className="dialog-backdrop" role="presentation"><section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="flow-reverse-title"><div className="dialog-heading"><div><span className="eyebrow">REVERSÃO FINANCEIRA</span><h2 id="flow-reverse-title">Reverter movimentação</h2><p>Uma nova entry oposta será criada; a original permanece no histórico.</p></div><button className="icon-button" type="button" aria-label="Fechar" disabled={saving} onClick={onClose}><X size={18} /></button></div><form onSubmit={submit}><p>{entryTypeLabels[entry.logical_entry_type]} · {formatLedgerMoney(entry.amount, entry.currency)}</p><label className="dialog-field">Motivo da reversão<textarea value={reason} rows={4} maxLength={2000} disabled={saving} required onChange={(event) => setReason(event.target.value)} /></label>{(validation || error) && <p className="dialog-error" role="alert">{validation || error}</p>}<div className="dialog-actions"><button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button><button className="button primary" type="submit" disabled={saving}>{saving ? "Revertendo…" : "Confirmar reversão"}</button></div></form></section></div>;
}

function FlowChart({ points }: { points: TimeseriesPoint[] }) {
  if (!points.length) return <div className="empty-state"><p>Sem dados para o gráfico no escopo selecionado.</p></div>;
  const width = 760;
  const height = 260;
  const pad = 34;
  const values = points.flatMap((point) => [Math.abs(Number(point.recognized_savings)), Math.abs(Number(point.reallocated)), Math.abs(Number(point.cumulative_balance))]);
  const max = Math.max(...values, 1);
  const innerHeight = height - pad * 2;
  const step = (width - pad * 2) / Math.max(points.length, 1);
  const y = (value: number) => height - pad - (Math.max(value, 0) / max) * innerHeight;
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"} ${pad + index * step + step / 2} ${y(Number(point.cumulative_balance))}`).join(" ");
  return <div style={{ overflowX: "auto" }}><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolução temporal de savings, reutilizações e saldo acumulado" style={{ width: "100%", minWidth: 560 }}><line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="currentColor" opacity="0.25" />{points.map((point, index) => {
    const x = pad + index * step + step * 0.2;
    const savingHeight = (Math.abs(Number(point.recognized_savings)) / max) * innerHeight;
    const reallocHeight = (Math.abs(Number(point.reallocated)) / max) * innerHeight;
    return <g key={`${point.bucket}-${index}`}><rect x={x} y={height - pad - savingHeight} width={Math.max(step * 0.22, 3)} height={savingHeight} fill="currentColor" opacity="0.75" /><rect x={x + step * 0.28} y={height - pad - reallocHeight} width={Math.max(step * 0.22, 3)} height={reallocHeight} fill="currentColor" opacity="0.35" /><title>{`${point.bucket}: saving ${point.recognized_savings}; reutilização ${point.reallocated}; saldo ${point.cumulative_balance}`}</title></g>;
  })}<path d={line} fill="none" stroke="currentColor" strokeWidth="2" /><text x={pad} y={18} fill="currentColor" fontSize="11">Barras: savings/reutilizações · Linha: saldo acumulado</text></svg></div>;
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

  const visibleAccounts = useMemo(() => provider === "all" ? accounts : accountsForProvider(accounts, provider), [accounts, provider]);
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
    api<CloudAccount[]>("/cloud-accounts").then((items) => { if (active) setAccounts(items); }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const optionQuery = queryString({ provider: globalQuery.provider, account_id: globalQuery.account_id, effective_from: range.from, effective_to: range.to });
    api<FlowOptions>(`/finops/flow/options?${optionQuery}`).then((value) => {
      if (!active) return;
      setOptions(value);
      if (!chartCurrency || !value.currencies.includes(chartCurrency)) setChartCurrency(value.currencies[0] || "");
      const bases = value.periodicities as Periodicity[];
      if (!chartBasis || !bases.includes(chartBasis)) setChartBasis(bases[0] || "");
    }).catch(() => undefined);
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
    ]).then(([nextSummary, nextSeries, nextBreakdowns]) => {
      if (!active) return;
      setSummary(nextSummary);
      setSeries(nextSeries);
      setBreakdowns(nextBreakdowns);
    }).catch((error) => {
      if (active) setAnalyticsError(error instanceof Error ? error.message : "Não foi possível carregar os indicadores do Fluxo.");
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [globalQuery, effectiveChartCurrency, effectiveChartBasis, reloadToken]);

  useEffect(() => {
    let active = true;
    setTableError("");
    const tableQuery = queryString({ ...globalQuery, entry_type: entryType === "all" ? undefined : entryType, search: search.trim() || undefined, page, page_size: 50 });
    api<FlowEntryPage>(`/finops/flow/entries?${tableQuery}`).then((value) => { if (active) setEntries(value); }).catch((error) => { if (active) setTableError(error instanceof Error ? error.message : "Não foi possível carregar as movimentações."); });
    return () => { active = false; };
  }, [globalQuery, entryType, search, page, reloadToken]);

  async function createEntry(payload: Record<string, unknown>) {
    setCreating(true); setMutationError(""); setSuccess("");
    try {
      await api<FlowEntry>("/finops/ledger/manual", { method: "POST", body: JSON.stringify(payload) });
      setCreateOpen(false); setSuccess("Movimentação registrada no Fluxo FinOps."); setReloadToken((value) => value + 1); setPage(1);
    } catch (error) { setMutationError(error instanceof Error ? error.message : "Não foi possível registrar a movimentação."); }
    finally { setCreating(false); }
  }

  async function reverseEntry(reason: string) {
    if (!reverseTarget) return;
    setReversing(true); setMutationError(""); setSuccess("");
    try {
      await api<FlowEntry>(`/finops/ledger/${reverseTarget.id}/reverse`, { method: "POST", body: JSON.stringify({ reason }) });
      setReverseTarget(null); setDetail(null); setSuccess("Reversão registrada. A movimentação original foi preservada."); setReloadToken((value) => value + 1);
    } catch (error) { setMutationError(error instanceof Error ? error.message : "Não foi possível reverter a movimentação."); }
    finally { setReversing(false); }
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

  return <div className="page-stack">
    <PageHeader eyebrow="FLUXO FINOPS" title="Fluxo" description="Savings reconhecidos, reutilizações e ajustes registrados no ledger. Fluxo não representa custo faturado pela cloud." actions={<button className="button primary" type="button" disabled={!accounts.length} onClick={() => { setMutationError(""); setSuccess(""); setCreateOpen(true); }}><Plus size={16} /> Nova movimentação</button>} />
    {success && <p className="form-success" role="status">{success}</p>}
    <section className="panel">
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12 }}>
        <label className="dialog-field">Período<select value={period} onChange={(event) => setPeriod(event.target.value as PeriodPreset)}><option value="this_month">Este mês</option><option value="previous_month">Mês anterior</option><option value="3m">Últimos 3 meses</option><option value="6m">Últimos 6 meses</option><option value="year">Este ano</option><option value="custom">Personalizado</option></select></label>
        <label className="dialog-field">Provider<select value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">Todos</option>{options.providers.map((value) => <option key={value} value={value}>{providerLabel(value)}</option>)}</select></label>
        <label className="dialog-field">Conta<select value={accountId} onChange={(event) => setAccountId(event.target.value)}><option value="all">Todas as contas</option>{visibleAccounts.map((account) => <option key={account.id} value={account.native_account_id}>{accountLabel(account)}</option>)}</select></label>
        <label className="dialog-field">Moeda<select value={currency} onChange={(event) => setCurrency(event.target.value)}><option value="all">Todas (sem consolidar)</option>{options.currencies.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className="dialog-field">Base financeira<select value={periodicity} onChange={(event) => setPeriodicity(event.target.value)}><option value="all">Todas (separadas)</option>{options.periodicities.map((value) => <option key={value} value={value}>{basisLabels[value as Periodicity] || value}</option>)}</select></label>
        <label className="dialog-field">Origem<select value={source} onChange={(event) => setSource(event.target.value)}><option value="all">Todas</option>{options.sources.map((value) => <option key={value} value={value}>{sourceLabel(value)}</option>)}</select></label>
      </div>
      {period === "custom" && <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 12 }}><label className="dialog-field">De<input type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} /></label><label className="dialog-field">Até<input type="date" value={customTo} max={localDateInput()} onChange={(event) => setCustomTo(event.target.value)} /></label></div>}
    </section>

    {analyticsError && <div className="opportunity-inline-error" role="alert"><div><strong>Indicadores indisponíveis.</strong><span>{analyticsError}</span></div></div>}
    <section aria-busy={loading}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", gap: 14 }}>
        {summary.map((item) => <article className="panel" key={`${item.currency}-${item.basis}`}><span className="eyebrow">{item.currency} · {basisLabels[item.basis]}</span><h3>{item.basis === "MONTHLY" ? "Run-rate reconhecido" : "Movimentações pontuais"}</h3><dl style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}><div><dt>Savings reconhecidos</dt><dd><strong>{formatLedgerMoney(item.recognized_savings, item.currency)}{item.basis === "MONTHLY" ? "/mês" : ""}</strong></dd></div><div><dt>Reutilizado</dt><dd><strong>{formatLedgerMoney(item.reallocated, item.currency)}{item.basis === "MONTHLY" ? "/mês" : ""}</strong></dd></div><div><dt>Ajustes líquidos</dt><dd><strong>{formatLedgerMoney(item.adjustment_net, item.currency)}{item.basis === "MONTHLY" ? "/mês" : ""}</strong></dd></div><div><dt>{item.basis === "MONTHLY" ? "Saldo líquido de run-rate" : "Saldo FinOps disponível"}</dt><dd><strong>{formatLedgerMoney(item.balance, item.currency)}{item.basis === "MONTHLY" ? "/mês" : ""}</strong></dd></div></dl></article>)}
        {!loading && !summary.length && <article className="panel"><div className="empty-state"><p>Nenhuma movimentação registrada no período.</p><button className="button primary" type="button" onClick={() => setCreateOpen(true)}>Nova movimentação</button></div></article>}
      </div>
    </section>

    <section className="panel">
      <div className="opportunity-workspace-toolbar"><div className="selection-summary"><strong>Evolução temporal</strong><small>Valores são agregados no backend por moeda e base financeira; o saldo acumulado inclui o saldo anterior ao período.</small></div><div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}><label className="dialog-field">Moeda do gráfico<select value={effectiveChartCurrency} disabled={currency !== "all"} onChange={(event) => setChartCurrency(event.target.value)}>{options.currencies.map((value) => <option key={value} value={value}>{value}</option>)}</select></label><label className="dialog-field">Base<select value={effectiveChartBasis} disabled={periodicity !== "all"} onChange={(event) => setChartBasis(event.target.value as Periodicity)}>{options.periodicities.map((value) => <option key={value} value={value}>{basisLabels[value as Periodicity]}</option>)}</select></label></div></div>
      <FlowChart points={activeSeries} />
    </section>

    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
      <section className="panel"><h3>Savings reconhecidos por conta</h3>{accountBreakdown.length ? accountBreakdown.map((item) => <div key={`${item.currency}-${item.basis}-${item.account_id}`} style={{ marginBottom: 12 }}><div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}><span>{item.account_name || item.account_id}</span><strong>{formatLedgerMoney(item.recognized_savings, item.currency)}</strong></div><div aria-hidden="true" style={{ height: 6, background: "currentColor", opacity: 0.12 }}><div style={{ height: "100%", width: `${Math.min(100, Math.abs(Number(item.recognized_savings)) / maxAccountSaving * 100)}%`, background: "currentColor" }} /></div></div>) : <p>Nenhum saving reconhecido para este recorte.</p>}</section>
      <section className="panel"><h3>Savings reconhecidos por origem</h3>{sourceBreakdown.length ? sourceBreakdown.map((item) => <div key={`${item.currency}-${item.basis}-${item.source}`} style={{ display: "flex", justifyContent: "space-between", gap: 12, marginBottom: 10 }}><span>{sourceLabel(item.source || "")}</span><strong>{formatLedgerMoney(item.recognized_savings, item.currency)}</strong></div>) : <p>Nenhum saving reconhecido para este recorte.</p>}</section>
    </div>

    <section className="panel">
      <div className="opportunity-workspace-toolbar"><div className="selection-summary"><strong>Movimentações</strong><small>{entries.total} movimentação(ões) no escopo. Reversões permanecem visíveis.</small></div><div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}><label className="dialog-field">Tipo<select value={entryType} onChange={(event) => { setEntryType(event.target.value); setPage(1); }}><option value="all">Todos</option><option value="SAVING">Saving</option><option value="REALLOCATION">Realocação</option><option value="ADJUSTMENT">Ajuste</option></select></label><label className="dialog-field">Busca<input value={search} placeholder="Descrição, recurso ou oportunidade" onChange={(event) => { setSearch(event.target.value); setPage(1); }} /></label></div></div>
      {tableError && <div className="opportunity-inline-error" role="alert"><div><strong>Não foi possível carregar as movimentações.</strong><span>{tableError}</span></div></div>}
      {!tableError && entries.items.length === 0 ? <div className="empty-state"><p>Nenhuma movimentação encontrada para os filtros selecionados.</p></div> : <div className="data-table-wrap" role="region" aria-label="Movimentações do Fluxo FinOps" tabIndex={0}><table className="data-table"><thead><tr><th>Data</th><th>Tipo</th><th>Descrição</th><th>Provider</th><th>Conta</th><th>Origem</th><th>Valor</th><th>Periodicidade</th><th>Status</th><th>Ações</th></tr></thead><tbody>{entries.items.map((entry) => <tr key={entry.id}><td>{effectiveDate(entry.effective_at)}</td><td>{entryTypeLabels[entry.logical_entry_type]}</td><td>{entry.description || "—"}</td><td>{providerLabel(entry.provider)}</td><td>{entry.account_name || entry.account_id}<small>{entry.account_id}</small></td><td>{sourceLabel(entry.logical_source)}{entry.is_reversal && <small>Reversal do ledger</small>}</td><td><strong>{entry.direction === "CREDIT" ? "+ " : "− "}{formatLedgerMoney(entry.amount, entry.currency)}</strong><small>{entry.currency}</small></td><td>{basisLabels[entry.periodicity]}</td><td>{entry.is_reversed ? "Revertida" : entry.is_reversal ? "Reversal" : "Registrada"}</td><td><div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}><button className="button ghost" type="button" onClick={() => setDetail(entry)}>Detalhes</button>{entry.opportunity_id && <Link className="button ghost" href={`/opportunities?opportunity_id=${encodeURIComponent(entry.opportunity_id)}`}><ExternalLink size={14} /> Ver oportunidade</Link>}{!entry.is_reversed && !entry.is_reversal && <button className="button ghost" type="button" onClick={() => { setMutationError(""); setReverseTarget(entry); }}><RotateCcw size={14} /> Reverter</button>}</div></td></tr>)}</tbody></table></div>}
      {entries.total_pages > 1 && <div className="pagination"><button className="button ghost" type="button" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Anterior</button><span>Página {page} de {entries.total_pages}</span><button className="button ghost" type="button" disabled={page >= entries.total_pages} onClick={() => setPage((value) => value + 1)}>Próxima</button></div>}
    </section>

    {detail && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDetail(null); }}><section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="flow-detail-title"><div className="dialog-heading"><div><span className="eyebrow">MOVIMENTAÇÃO</span><h2 id="flow-detail-title">Detalhes</h2></div><button className="icon-button" type="button" aria-label="Fechar" onClick={() => setDetail(null)}><X size={18} /></button></div><dl style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}><div><dt>Tipo</dt><dd>{entryTypeLabels[detail.logical_entry_type]}</dd></div><div><dt>Direção</dt><dd>{detail.direction === "CREDIT" ? "Crédito" : "Débito"}</dd></div><div><dt>Valor</dt><dd>{formatLedgerMoney(detail.amount, detail.currency)}</dd></div><div><dt>Currency</dt><dd>{detail.currency}</dd></div><div><dt>Provider</dt><dd>{providerLabel(detail.provider)}</dd></div><div><dt>Conta</dt><dd>{detail.account_name || detail.account_id}</dd></div><div><dt>Data efetiva</dt><dd>{effectiveDate(detail.effective_at)}</dd></div><div><dt>Criado em</dt><dd>{createdAt(detail.created_at)}</dd></div><div><dt>Origem</dt><dd>{sourceLabel(detail.logical_source)}</dd></div><div><dt>Criado por</dt><dd>{detail.created_by_name || detail.created_by || "Sistema"}</dd></div><div><dt>Periodicidade</dt><dd>{basisLabels[detail.periodicity]}</dd></div><div><dt>Status</dt><dd>{detail.is_reversed ? "Revertida" : detail.is_reversal ? "Reversal" : "Registrada"}</dd></div></dl><p><strong>Descrição:</strong> {detail.description || "—"}</p>{detail.opportunity_id && <p><strong>Oportunidade:</strong> {detail.opportunity_title || detail.opportunity_id}<br /><strong>Service:</strong> {detail.opportunity_service || "Não informado"}<br /><strong>Treatment event:</strong> {detail.source_event_id || "—"}<br /><Link href={`/opportunities?opportunity_id=${encodeURIComponent(detail.opportunity_id)}`}>Ver oportunidade associada</Link></p>}{detail.reversal_of_id && <p><strong>Original:</strong> {detail.reversal_of_id}</p>}{detail.reversed_by_id && <p><strong>Reversal:</strong> {detail.reversed_by_id}</p>}</section></div>}
    {createOpen && <ManualEntryDialog accounts={accounts} saving={creating} error={mutationError} onClose={() => !creating && setCreateOpen(false)} onSubmit={createEntry} />}
    {reverseTarget && <ReversalDialog entry={reverseTarget} saving={reversing} error={mutationError} onClose={() => !reversing && setReverseTarget(null)} onSubmit={reverseEntry} />}
  </div>;
}
