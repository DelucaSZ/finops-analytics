"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Plus, RotateCcw, X } from "lucide-react";
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
type Currency = "BRL" | "USD";
type Periodicity = "ONE_TIME" | "MONTHLY";

type FinOpsLedgerEntry = {
  id: string;
  entry_type: EntryType;
  direction: Direction;
  provider: string;
  cloud_account_id: number;
  account_id: string;
  amount: string;
  currency: string;
  effective_at: string;
  source: string;
  description: string | null;
  periodicity: Periodicity;
  reference_period_start: string | null;
  reference_period_end: string | null;
  created_by: string | null;
  created_at: string;
  reversal_of_id: string | null;
  is_reversed: boolean;
  reversed_by_id: string | null;
};

type FinOpsLedgerPage = {
  items: FinOpsLedgerEntry[];
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

function localDateInput(date = new Date()): string {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function effectiveDate(value: string): string {
  const [year, month, day] = value.slice(0, 10).split("-");
  return year && month && day ? `${day}/${month}/${year}` : value;
}

function createdAt(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function providerLabel(provider: string): string {
  return provider.toUpperCase();
}

function periodicityLabel(periodicity: Periodicity): string {
  return periodicity === "MONTHLY" ? "/ mês" : "pontual";
}

function accountLabel(account: CloudAccount): string {
  return account.name ? `${account.name} · ${account.native_account_id}` : account.native_account_id;
}

function ManualEntryDialog({
  accounts,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  accounts: CloudAccount[];
  saving: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const initialProvider = accounts.find((account) => account.enabled)?.provider || accounts[0]?.provider || "aws";
  const [entryType, setEntryType] = useState<EntryType>("SAVING");
  const [provider, setProvider] = useState(initialProvider);
  const initialAccounts = accountsForProvider(accounts, initialProvider);
  const [cloudAccountId, setCloudAccountId] = useState(String(initialAccounts[0]?.id || ""));
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState<Currency>(defaultCurrencyForProvider(initialProvider, "USD"));
  const [effective, setEffective] = useState(localDateInput());
  const [periodicity, setPeriodicity] = useState<Periodicity>("MONTHLY");
  const [adjustmentDirection, setAdjustmentDirection] = useState<Direction>("CREDIT");
  const [description, setDescription] = useState("");
  const [validation, setValidation] = useState("");
  const requestId = useRef("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const visibleAccounts = useMemo(
    () => accountsForProvider(accounts, provider),
    [accounts, provider],
  );
  const direction = directionForEntryType(entryType, adjustmentDirection);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, saving]);

  function changeProvider(nextProvider: string) {
    const nextAccounts = accountsForProvider(accounts, nextProvider);
    setProvider(nextProvider);
    setCloudAccountId(String(nextAccounts[0]?.id || ""));
    setCurrency(defaultCurrencyForProvider(nextProvider, currency));
  }

  function changeType(nextType: EntryType) {
    setEntryType(nextType);
    if (nextType === "SAVING") setPeriodicity("MONTHLY");
    else setPeriodicity("ONE_TIME");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setValidation("");
    const normalizedAmount = normalizePositiveDecimal(amount);
    if (!cloudAccountId) {
      setValidation("Selecione uma conta para a movimentação.");
      return;
    }
    if (!normalizedAmount) {
      setValidation("Informe um valor positivo com até 8 casas decimais.");
      return;
    }
    if (!effective || effective > localDateInput()) {
      setValidation("A data efetiva não pode estar no futuro.");
      return;
    }
    if (description.trim().length < 3) {
      setValidation("Descreva o contexto da movimentação com pelo menos 3 caracteres.");
      return;
    }
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
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <section
        className="decision-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="manual-finops-title"
      >
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">FLUXO FINOPS</span>
            <h2 id="manual-finops-title">Nova movimentação</h2>
            <p>Registre um fato financeiro manual no mesmo ledger das oportunidades tratadas.</p>
          </div>
          <button
            ref={closeRef}
            className="icon-button"
            type="button"
            aria-label="Fechar"
            disabled={saving}
            onClick={onClose}
          >
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit}>
          <label className="dialog-field">
            Tipo
            <select
              value={entryType}
              disabled={saving}
              onChange={(event) => changeType(event.target.value as EntryType)}
            >
              {MANUAL_ENTRY_TYPES.map((type) => (
                <option key={type} value={type}>{entryTypeLabels[type as EntryType]}</option>
              ))}
            </select>
          </label>

          <label className="dialog-field">
            Direção
            {entryType === "ADJUSTMENT" ? (
              <select
                value={adjustmentDirection}
                disabled={saving}
                onChange={(event) => setAdjustmentDirection(event.target.value as Direction)}
              >
                <option value="CREDIT">Crédito</option>
                <option value="DEBIT">Débito</option>
              </select>
            ) : (
              <input value={direction === "CREDIT" ? "Crédito" : "Débito"} readOnly />
            )}
          </label>

          <label className="dialog-field">
            Provider
            <select
              value={provider}
              disabled={saving}
              onChange={(event) => changeProvider(event.target.value)}
            >
              {Array.from(new Set(accounts.map((account) => account.provider))).map((value) => (
                <option key={value} value={value}>{providerLabel(value)}</option>
              ))}
            </select>
          </label>

          <label className="dialog-field">
            Conta
            <select
              value={cloudAccountId}
              disabled={saving}
              required
              onChange={(event) => setCloudAccountId(event.target.value)}
            >
              <option value="">Selecione uma conta</option>
              {visibleAccounts.map((account) => (
                <option key={account.id} value={account.id}>{accountLabel(account)}</option>
              ))}
            </select>
          </label>

          <label className="dialog-field">
            Valor
            <input
              value={amount}
              inputMode="decimal"
              autoComplete="off"
              placeholder="2500.00"
              disabled={saving}
              required
              onChange={(event) => setAmount(event.target.value)}
            />
          </label>

          <label className="dialog-field">
            Moeda
            <select
              value={currency}
              disabled={saving}
              onChange={(event) => setCurrency(event.target.value as Currency)}
            >
              <option value="BRL">BRL — Real brasileiro</option>
              <option value="USD">USD — Dólar americano</option>
            </select>
          </label>

          <label className="dialog-field">
            Data da movimentação
            <input
              type="date"
              value={effective}
              max={localDateInput()}
              disabled={saving}
              required
              onChange={(event) => setEffective(event.target.value)}
            />
          </label>

          {entryType === "SAVING" && (
            <label className="dialog-field">
              Periodicidade
              <select
                value={periodicity}
                disabled={saving}
                onChange={(event) => setPeriodicity(event.target.value as Periodicity)}
              >
                <option value="MONTHLY">Mensal</option>
                <option value="ONE_TIME">Pontual</option>
              </select>
            </label>
          )}

          <label className="dialog-field">
            Descrição
            <textarea
              value={description}
              rows={4}
              maxLength={2000}
              disabled={saving}
              required
              placeholder="Contexto para auditoria da movimentação"
              onChange={(event) => setDescription(event.target.value)}
            />
          </label>

          <p className="dialog-field">
            {entryTypeLabels[entryType]} · {direction === "CREDIT" ? "Crédito" : "Débito"} · {currency}
            {entryType === "SAVING" ? ` · ${periodicity === "MONTHLY" ? "mensal" : "pontual"}` : ""}
          </p>
          {(validation || error) && <p className="dialog-error" role="alert">{validation || error}</p>}
          <div className="dialog-actions">
            <button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button>
            <button className="button primary" type="submit" disabled={saving || !visibleAccounts.length}>
              {saving ? "Salvando…" : "Registrar movimentação"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function ReversalDialog({
  entry,
  saving,
  error,
  onClose,
  onSubmit,
}: {
  entry: FinOpsLedgerEntry;
  saving: boolean;
  error: string;
  onClose: () => void;
  onSubmit: (reason: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [validation, setValidation] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = reason.trim();
    if (normalized.length < 3) {
      setValidation("Informe o motivo da reversão.");
      return;
    }
    setValidation("");
    await onSubmit(normalized);
  }

  return (
    <div className="dialog-backdrop" role="presentation">
      <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="reverse-finops-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">REVERSÃO FINANCEIRA</span>
            <h2 id="reverse-finops-title">Reverter movimentação</h2>
            <p>
              Será criada uma nova entry com o mesmo valor e moeda, em direção oposta. O registro original será preservado.
            </p>
          </div>
          <button className="icon-button" type="button" aria-label="Fechar" disabled={saving} onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <form onSubmit={submit}>
          <p>
            {entryTypeLabels[entry.entry_type]} · {formatLedgerMoney(entry.amount, entry.currency)} · {providerLabel(entry.provider)}
          </p>
          <label className="dialog-field">
            Motivo da reversão
            <textarea
              value={reason}
              rows={4}
              maxLength={2000}
              disabled={saving}
              required
              placeholder="Ex.: movimentação cadastrada na conta incorreta"
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          {(validation || error) && <p className="dialog-error" role="alert">{validation || error}</p>}
          <div className="dialog-actions">
            <button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button>
            <button className="button primary" type="submit" disabled={saving}>
              {saving ? "Revertendo…" : "Confirmar reversão"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default function FinOpsLedgerPage() {
  const [entries, setEntries] = useState<FinOpsLedgerEntry[]>([]);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [success, setSuccess] = useState("");
  const [creating, setCreating] = useState(false);
  const [reversing, setReversing] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [reverseTarget, setReverseTarget] = useState<FinOpsLedgerEntry | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setListError("");
    Promise.all([
      api<FinOpsLedgerPage>(`/finops/ledger?page=${page}&page_size=50`),
      api<CloudAccount[]>("/cloud-accounts"),
    ])
      .then(([ledger, accountList]) => {
        if (!active) return;
        setEntries(ledger.items);
        setTotalPages(ledger.total_pages);
        setTotal(ledger.total);
        setAccounts(accountList);
      })
      .catch((error) => {
        if (!active) return;
        setListError(error instanceof Error ? error.message : "Não foi possível carregar as movimentações.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [page, reloadToken]);

  async function createEntry(payload: Record<string, unknown>) {
    setCreating(true);
    setMutationError("");
    setSuccess("");
    try {
      await api<FinOpsLedgerEntry>("/finops/ledger/manual", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setCreateOpen(false);
      setSuccess("Movimentação registrada no Fluxo FinOps.");
      setPage(1);
      setReloadToken((value) => value + 1);
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
      await api<FinOpsLedgerEntry>(`/finops/ledger/${reverseTarget.id}/reverse`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setReverseTarget(null);
      setSuccess("Reversão registrada. A movimentação original foi preservada.");
      setReloadToken((value) => value + 1);
    } catch (error) {
      setMutationError(error instanceof Error ? error.message : "Não foi possível reverter a movimentação.");
    } finally {
      setReversing(false);
    }
  }

  const accountById = useMemo(
    () => new Map(accounts.map((account) => [account.id, account])),
    [accounts],
  );

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="FLUXO FINOPS"
        title="Movimentações"
        description="Cadastro administrativo mínimo do ledger. Dashboard, KPIs e gráficos serão tratados na próxima etapa."
        actions={(
          <button
            className="button primary"
            type="button"
            disabled={loading || !accounts.length}
            onClick={() => {
              setMutationError("");
              setSuccess("");
              setCreateOpen(true);
            }}
          >
            <Plus size={16} /> Nova movimentação
          </button>
        )}
      />

      {success && <p className="form-success" role="status">{success}</p>}
      {listError && (
        <div className="opportunity-inline-error" role="alert">
          <div><strong>Não foi possível carregar as movimentações.</strong><span>{listError}</span></div>
          <button className="button ghost" type="button" onClick={() => setReloadToken((value) => value + 1)}>Tentar novamente</button>
        </div>
      )}

      <section className="panel" aria-busy={loading}>
        <div className="opportunity-workspace-toolbar">
          <div className="selection-summary">
            <span>{total} movimentação(ões) registrada(s)</span>
            <small>Valores permanecem separados por moeda; não há conversão cambial.</small>
          </div>
        </div>

        {loading && <div className="table-loading-bar" role="status"><span /> Carregando movimentações…</div>}
        {!loading && !listError && entries.length === 0 ? (
          <div className="empty-state">
            <p>Nenhuma movimentação registrada.</p>
            <button className="button primary" type="button" onClick={() => setCreateOpen(true)}>
              Nova movimentação
            </button>
          </div>
        ) : (
          <div className="data-table-wrap" role="region" aria-label="Movimentações do Fluxo FinOps" tabIndex={0}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Data</th>
                  <th scope="col">Tipo</th>
                  <th scope="col">Provider</th>
                  <th scope="col">Conta</th>
                  <th scope="col">Descrição</th>
                  <th scope="col">Valor</th>
                  <th scope="col">Origem / auditoria</th>
                  <th scope="col">Ação</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => {
                  const account = accountById.get(entry.cloud_account_id);
                  return (
                    <tr key={entry.id}>
                      <td>{effectiveDate(entry.effective_at)}</td>
                      <td>
                        <strong>{entryTypeLabels[entry.entry_type]}</strong>
                        <small>{entry.direction === "CREDIT" ? "Crédito" : "Débito"} · {periodicityLabel(entry.periodicity)}</small>
                        {entry.is_reversed && <small>Revertida</small>}
                        {entry.reversal_of_id && <small>Reversão de {entry.reversal_of_id.slice(0, 8)}</small>}
                      </td>
                      <td>{providerLabel(entry.provider)}</td>
                      <td>{account?.name || entry.account_id}<small>{entry.account_id}</small></td>
                      <td>{entry.description || "—"}</td>
                      <td>
                        <strong>{entry.direction === "CREDIT" ? "+" : "−"}{formatLedgerMoney(entry.amount, entry.currency)}</strong>
                        <small>{entry.currency}</small>
                      </td>
                      <td>
                        <strong>{sourceLabel(entry.source)}</strong>
                        <small>Registrado em {createdAt(entry.created_at)}</small>
                        <small>{entry.created_by ? `Autor ${entry.created_by.slice(0, 8)}` : "Autor do sistema"}</small>
                      </td>
                      <td>
                        {!entry.is_reversed && !entry.reversal_of_id ? (
                          <button
                            className="button ghost"
                            type="button"
                            onClick={() => {
                              setMutationError("");
                              setSuccess("");
                              setReverseTarget(entry);
                            }}
                          >
                            <RotateCcw size={15} /> Reverter
                          </button>
                        ) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <button className="button ghost" type="button" disabled={loading || page <= 1} onClick={() => setPage((value) => value - 1)}>Anterior</button>
            <span>Página {page} de {totalPages}</span>
            <button className="button ghost" type="button" disabled={loading || page >= totalPages} onClick={() => setPage((value) => value + 1)}>Próxima</button>
          </div>
        )}
      </section>

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
