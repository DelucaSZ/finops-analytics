"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { History, LockKeyhole, RefreshCw, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { periodCloseResultMessage } from "@/lib/opportunity-archive.mjs";
import {
  buildHistorySnapshotQuery,
  chooseHistoryCycle,
  cycleStateLabel,
  historyMoneyRows,
} from "@/lib/opportunity-history.mjs";
import { queryKeys } from "@/lib/query-keys.mjs";
import { invalidateApiQueries } from "@/lib/server-state";
import styles from "./page.module.css";

type MoneyTotal = { currency: string; amount: string | number };
type Coverage = { total: number; success: number; failed: number; running: number };
type Cycle = {
  id: string;
  label: string;
  period_start: string;
  period_end: string;
  status: "OPEN" | "CLOSED";
  timezone: string;
  created_at: string;
  closed_at: string | null;
  closed_by: string | null;
  close_reason: string | null;
  snapshot_count: number;
  totals: {
    total?: number;
    by_status?: Record<string, number>;
    by_severity?: Record<string, number>;
    potential_savings?: MoneyTotal[];
    current_cost?: MoneyTotal[];
    providers?: number;
    accounts?: number;
  };
  coverage: Coverage;
};
type Snapshot = {
  id: string;
  cycle_id: string;
  opportunity_id: string | null;
  provider: string;
  account_id: string;
  account_name: string | null;
  region: string | null;
  service: string;
  resource_type: string | null;
  resource_id: string;
  resource_name: string | null;
  rule_key: string;
  title: string;
  description: string;
  status: string;
  presence_status: string;
  needs_review: boolean;
  archived: boolean;
  archive_reason: string | null;
  treated_at: string | null;
  rejected_at: string | null;
  resolved_externally_at: string | null;
  treatment_note: string | null;
  rejection_reason: string | null;
  rejection_note: string | null;
  current_monthly_cost: string | number;
  estimated_monthly_savings: string | number;
  currency: string;
  severity: string;
  confidence: string;
  first_seen_at: string;
  last_seen_at: string;
  first_observed_in_cycle_at: string;
  last_observed_in_cycle_at: string;
  occurrence_count_in_cycle: number;
  total_occurrence_count: number;
  first_collection_run_id_in_cycle: string | null;
  last_collection_run_id_in_cycle: string | null;
  captured_at: string;
};
type SnapshotPage = {
  items: Snapshot[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};
type PeriodClosePreview = {
  cycle_id: string;
  label: string;
  period_start: string;
  period_end: string;
  cycle_status: string;
  snapshots_to_create: number;
  collection_runs: number;
  failed_collection_runs: number;
  running_collection_runs: number;
  archive: {
    matched: number;
    to_archive: number;
    already_archived: number;
    by_status: Record<string, number>;
    by_provider: Record<string, number>;
    account_count: number;
    currencies: Array<{
      currency: string;
      current_monthly_cost: string | number;
      estimated_monthly_savings: string | number;
    }>;
    filter_hash: string;
    generated_at: string;
    archive_all: boolean;
  };
};
type PeriodCloseResult = {
  cycle_closed: boolean;
  cycle_id: string;
  snapshots_created: number;
  collection_runs: number;
  failed_collection_runs: number;
  matched: number;
  archived: number;
  already_archived: number;
  failed: number;
  correlation_id: string;
};

function statusLabel(status: string) {
  if (status === "treated") return "Tratada";
  if (status === "rejected") return "Rejeitada";
  return "Aberta";
}

function presenceLabel(status: string) {
  if (status === "missing") return "Ausente";
  if (status === "resolved_externally") return "Resolvida externamente";
  return "Ativa";
}

export default function OpportunityHistoryCyclesPage() {
  const [cycles, setCycles] = useState<Cycle[]>([]);
  const [cycleId, setCycleId] = useState("");
  const [snapshots, setSnapshots] = useState<SnapshotPage>({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
  const [selected, setSelected] = useState<Snapshot | null>(null);
  const [page, setPage] = useState(1);
  const [provider, setProvider] = useState("");
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(false);
  const [closePreview, setClosePreview] = useState<PeriodClosePreview | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const cycle = useMemo(() => cycles.find((item) => item.id === cycleId) ?? null, [cycles, cycleId]);
  const savings = historyMoneyRows(cycle?.totals, "potential_savings") as MoneyTotal[];
  const costs = historyMoneyRows(cycle?.totals, "current_cost") as MoneyTotal[];

  async function loadCycles(preferredId = cycleId) {
    setError("");
    const current = await api<Cycle>("/opportunity-history/cycles/current");
    const response = await api<{ items: Cycle[]; total: number }>("/opportunity-history/cycles");
    const items = response.items.some((item) => item.id === current.id)
      ? response.items
      : [current, ...response.items];
    setCycles(items);
    const next = chooseHistoryCycle(items, preferredId) as Cycle | null;
    setCycleId(next?.id ?? "");
    return next;
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadCycles().catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "Não foi possível carregar os ciclos históricos.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
    // Initial bootstrap only. Subsequent refreshes are explicit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!cycleId) return;
    const chosen = cycles.find((item) => item.id === cycleId);
    setSelected(null);
    if (!chosen || chosen.status !== "CLOSED") {
      setSnapshots({ items: [], total: 0, page: 1, page_size: 50, total_pages: 0 });
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      const query = buildHistorySnapshotQuery({ cycleId, page, pageSize: 50, provider, status, severity, search });
      api<SnapshotPage>(`/opportunity-history/snapshots?${query}`).then((response) => {
        if (active) setSnapshots(response);
      }).catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Não foi possível carregar os snapshots do ciclo.");
      });
    }, search ? 250 : 0);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [cycleId, cycles, page, provider, search, severity, status]);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      await loadCycles(cycleId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível atualizar o histórico.");
    } finally {
      setLoading(false);
    }
  }

  function periodClosePayload() {
    const filters: Record<string, string> = {};
    if (provider) filters.provider = provider;
    if (status) filters.status = status;
    if (severity) filters.severity = severity;
    if (search.trim()) filters.search = search.trim();
    return {
      cycle_id: cycle?.id || "",
      filters,
      archive_all: Object.keys(filters).length === 0,
    };
  }

  async function previewSelectedCycleClose() {
    if (!cycle || cycle.status !== "OPEN") return;
    setClosing(true);
    setError("");
    setMessage("");
    try {
      const preview = await api<PeriodClosePreview>("/opportunities/period-close/preview", {
        method: "POST",
        body: JSON.stringify(periodClosePayload()),
      });
      setClosePreview(preview);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível preparar o fechamento operacional.");
    } finally {
      setClosing(false);
    }
  }

  async function confirmSelectedCycleClose() {
    if (!cycle || !closePreview || closing || closePreview.running_collection_runs > 0) return;
    setClosing(true);
    setError("");
    try {
      const result = await api<PeriodCloseResult>("/opportunities/period-close", {
        method: "POST",
        body: JSON.stringify(periodClosePayload()),
      });
      setClosePreview(null);
      setMessage(periodCloseResultMessage(result, cycle.label));
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.dashboard.all);
      await loadCycles(cycle.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível fechar o período operacional.");
    } finally {
      setClosing(false);
    }
  }

  return (
    <section className={styles.page}>
      <PageHeader
        eyebrow="OPORTUNIDADES"
        title="Histórico de ciclos"
        description="Snapshots imutáveis por período fechado, separados do backlog e do arquivamento operacional."
        actions={(
          <button className="button secondary" type="button" onClick={refresh} disabled={loading}>
            <RefreshCw size={16} /> {loading ? "Atualizando…" : "Atualizar"}
          </button>
        )}
      />

      <div className={styles.switcher} aria-label="Visões de histórico">
        <span><History size={14} /> Ciclos fechados</span>
        <Link href="/opportunities?view=history">Arquivadas atualmente / Histórico legado</Link>
        <Link href="/opportunities">Backlog operacional</Link>
      </div>

      {message && <div className="alert success" role="status">{message}</div>}
      {error && <div className={styles.error} role="alert">{error}</div>}

      <div className={styles.controls}>
        <div className={styles.field}>
          <label htmlFor="history-cycle">Período histórico</label>
          <select
            id="history-cycle"
            value={cycleId}
            onChange={(event) => { setCycleId(event.target.value); setPage(1); }}
          >
            {cycles.map((item) => (
              <option value={item.id} key={item.id}>
                {item.label} — {cycleStateLabel(item.status)}
              </option>
            ))}
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="history-provider">Cloud</label>
          <select id="history-provider" value={provider} onChange={(event) => { setProvider(event.target.value); setPage(1); }}>
            <option value="">Todas</option>
            <option value="aws">AWS</option>
            <option value="oci">OCI</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="history-status">Status no fechamento</label>
          <select id="history-status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
            <option value="">Todos</option>
            <option value="open">Aberta</option>
            <option value="treated">Tratada</option>
            <option value="rejected">Rejeitada</option>
          </select>
        </div>
        <div className={styles.field}>
          <label htmlFor="history-severity">Severidade</label>
          <select id="history-severity" value={severity} onChange={(event) => { setSeverity(event.target.value); setPage(1); }}>
            <option value="">Todas</option>
            <option value="high">Alta</option>
            <option value="medium">Média</option>
            <option value="low">Baixa</option>
          </select>
        </div>
      </div>

      <div className={styles.field}>
        <label htmlFor="history-search">Buscar no snapshot</label>
        <input
          id="history-search"
          type="search"
          value={search}
          onChange={(event) => { setSearch(event.target.value); setPage(1); }}
          placeholder="Recurso, título, conta ou ID"
        />
      </div>

      {cycle && (
        <div className={styles.banner}>
          <strong>{cycle.label} · {cycleStateLabel(cycle.status)}</strong>
          <span className={styles.secondary}>
            {formatDate(cycle.period_start)} até {formatDate(cycle.period_end)} · timezone {cycle.timezone}
            {cycle.closed_at ? ` · fechado em ${formatDate(cycle.closed_at)}` : " · Prévia — período ainda não fechado"}
          </span>
          {cycle.status === "OPEN" && (
            <div style={{ marginTop: 12 }}>
              <button className="button" type="button" disabled={closing} onClick={previewSelectedCycleClose}>
                <LockKeyhole size={16} /> {closing ? "Preparando…" : "Fechar período"}
              </button>
              {cycle.coverage.running > 0 && (
                <span className={styles.secondary} style={{ marginLeft: 12 }}>
                  {cycle.coverage.running} coleta(s) em andamento impedirão o fechamento.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {cycle && (
        <div className={styles.summary}>
          <div className={styles.card}>
            <small>Oportunidades no snapshot</small>
            <strong>{cycle.status === "CLOSED" ? cycle.snapshot_count : "—"}</strong>
          </div>
          <div className={styles.card}>
            <small>Economia potencial</small>
            <div className={styles.moneyList}>
              {savings.length ? savings.map((row) => <strong key={row.currency}>{formatMoney(row.amount, row.currency)}/mês</strong>) : <strong>—</strong>}
            </div>
          </div>
          <div className={styles.card}>
            <small>Custo atual no fechamento</small>
            <div className={styles.moneyList}>
              {costs.length ? costs.map((row) => <strong key={row.currency}>{formatMoney(row.amount, row.currency)}/mês</strong>) : <strong>—</strong>}
            </div>
          </div>
          <div className={styles.card}>
            <small>Cobertura de coletas</small>
            <strong>{cycle.coverage.total}</strong>
            <span className={styles.secondary}>{cycle.coverage.success} sucesso · {cycle.coverage.failed} falha · {cycle.coverage.running} em andamento</span>
          </div>
        </div>
      )}

      {cycle?.status === "OPEN" ? (
        <div className={styles.empty}>
          Prévia — período ainda não fechado. Snapshots definitivos são materializados somente no fechamento.
        </div>
      ) : (
        <div className={styles.tableCard}>
          <div className={styles.tableScroll}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Oportunidade</th>
                  <th>Conta / Cloud</th>
                  <th>Status</th>
                  <th>Severidade</th>
                  <th>Custo</th>
                  <th>Economia</th>
                  <th>Observações</th>
                  <th>Última observação</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <button type="button" className={styles.rowButton} onClick={() => setSelected(item)}>
                        <strong>{item.title}</strong>
                        <span>{item.resource_name || item.resource_id}</span>
                      </button>
                    </td>
                    <td>{item.account_name || item.account_id}<div className={styles.secondary}>{providerLabel(item.provider)}</div></td>
                    <td><span className={styles.pill}>{statusLabel(item.status)}</span></td>
                    <td>{item.severity}</td>
                    <td>{formatMoney(item.current_monthly_cost, item.currency)}</td>
                    <td>{formatMoney(item.estimated_monthly_savings, item.currency)}</td>
                    <td>{item.occurrence_count_in_cycle}</td>
                    <td>{formatDate(item.last_observed_in_cycle_at)}</td>
                  </tr>
                ))}
                {!snapshots.items.length && (
                  <tr><td colSpan={8} className={styles.empty}>Nenhum snapshot encontrado para este ciclo e filtros.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className={styles.footer}>
            <span>{snapshots.total} snapshots · página {snapshots.page || 1} de {snapshots.total_pages || 1}</span>
            <div className={styles.footerActions}>
              <button className="button secondary" type="button" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Anterior</button>
              <button className="button secondary" type="button" disabled={!snapshots.total_pages || page >= snapshots.total_pages} onClick={() => setPage((value) => value + 1)}>Próxima</button>
            </div>
          </div>
        </div>
      )}

      {selected && (
        <article className={styles.detail} aria-label={`Snapshot ${selected.title}`}>
          <div className={styles.detailHeader}>
            <div>
              <small>Snapshot do período</small>
              <h2>{selected.title}</h2>
              <p>{selected.description}</p>
            </div>
            <button className="button secondary" type="button" onClick={() => setSelected(null)}>Fechar detalhe</button>
          </div>
          <dl className={styles.detailGrid}>
            <div><dt>Cloud</dt><dd>{providerLabel(selected.provider)}</dd></div>
            <div><dt>Conta</dt><dd>{selected.account_name || selected.account_id}</dd></div>
            <div><dt>Recurso</dt><dd>{selected.resource_name || selected.resource_id}</dd></div>
            <div><dt>Regra</dt><dd>{selected.rule_key}</dd></div>
            <div><dt>Serviço / Região</dt><dd>{selected.service} · {selected.region || "—"}</dd></div>
            <div><dt>Status no fechamento</dt><dd>{statusLabel(selected.status)}</dd></div>
            <div><dt>Presença no fechamento</dt><dd>{presenceLabel(selected.presence_status)}</dd></div>
            <div><dt>Severidade / confiança</dt><dd>{selected.severity} · {selected.confidence}</dd></div>
            <div><dt>Arquivada operacionalmente</dt><dd>{selected.archived ? `Sim${selected.archive_reason ? ` · ${selected.archive_reason}` : ""}` : "Não"}</dd></div>
            <div><dt>Custo no período</dt><dd>{formatMoney(selected.current_monthly_cost, selected.currency)}/mês</dd></div>
            <div><dt>Economia estimada</dt><dd>{formatMoney(selected.estimated_monthly_savings, selected.currency)}/mês</dd></div>
            <div><dt>Primeira observação no ciclo</dt><dd>{formatDate(selected.first_observed_in_cycle_at)}</dd></div>
            <div><dt>Última observação no ciclo</dt><dd>{formatDate(selected.last_observed_in_cycle_at)}</dd></div>
            <div><dt>Observações no ciclo</dt><dd>{selected.occurrence_count_in_cycle}</dd></div>
            <div><dt>Primeira detecção histórica</dt><dd>{formatDate(selected.first_seen_at)}</dd></div>
            <div><dt>Última detecção conhecida no fechamento</dt><dd>{formatDate(selected.last_seen_at)}</dd></div>
            <div><dt>Última CollectionRun do ciclo</dt><dd>{selected.last_collection_run_id_in_cycle || "—"}</dd></div>
          </dl>
          {selected.rejection_reason && <p><strong>Motivo da rejeição:</strong> {selected.rejection_reason}{selected.rejection_note ? ` — ${selected.rejection_note}` : ""}</p>}
          {selected.treatment_note && <p><strong>Tratamento:</strong> {selected.treatment_note}</p>}
          {selected.opportunity_id && (
            <p><Link href={`/opportunities?resource_id=${encodeURIComponent(selected.resource_id)}`}>Ver oportunidade atual</Link> <span className={styles.secondary}>— o estado atual é independente deste snapshot.</span></p>
          )}
        </article>
      )}

      {closePreview && cycle && (
        <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget && !closing) setClosePreview(null);
        }}>
          <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="period-close-title">
            <div className="dialog-heading">
              <div>
                <span className="eyebrow">FECHAMENTO OPERACIONAL</span>
                <h2 id="period-close-title">Fechar período {closePreview.label}</h2>
                <p>O snapshot histórico e o arquivamento operacional são operações diferentes, executadas na mesma transação.</p>
              </div>
              <button className="icon-button" type="button" aria-label="Fechar" disabled={closing} onClick={() => setClosePreview(null)}><X size={18} /></button>
            </div>
            <dl className={styles.detailGrid}>
              <div><dt>Snapshots a gerar</dt><dd>{closePreview.snapshots_to_create.toLocaleString("pt-BR")}</dd></div>
              <div><dt>Itens operacionais a arquivar</dt><dd>{closePreview.archive.to_archive.toLocaleString("pt-BR")}</dd></div>
              <div><dt>Já arquivados no mesmo escopo</dt><dd>{closePreview.archive.already_archived.toLocaleString("pt-BR")}</dd></div>
              <div><dt>Coletas no período</dt><dd>{closePreview.collection_runs}</dd></div>
              <div><dt>Coletas com falha</dt><dd>{closePreview.failed_collection_runs}</dd></div>
              <div><dt>Coletas em andamento</dt><dd>{closePreview.running_collection_runs}</dd></div>
              <div><dt>Escopo operacional</dt><dd>{closePreview.archive.archive_all ? "Todo o backlog ativo" : [provider && `Cloud ${providerLabel(provider)}`, status && `Status ${statusLabel(status)}`, severity && `Severidade ${severity}`, search.trim() && `Busca “${search.trim()}”`].filter(Boolean).join(" · ")}</dd></div>
              <div><dt>Moedas</dt><dd>{closePreview.archive.currencies.map((item) => item.currency).join(" / ") || "—"}</dd></div>
            </dl>
            {closePreview.failed_collection_runs > 0 && (
              <div className="alert" role="status">
                {closePreview.failed_collection_runs} coleta(s) falharam neste período. O histórico refletirá apenas dados efetivamente observados.
              </div>
            )}
            {closePreview.running_collection_runs > 0 && (
              <div className="alert error" role="alert">
                Não é possível fechar este período enquanto existem {closePreview.running_collection_runs} coleta(s) em andamento.
              </div>
            )}
            <div className="dialog-actions">
              <button className="button ghost" type="button" disabled={closing} onClick={() => setClosePreview(null)}>Cancelar</button>
              <button className="button primary" type="button" disabled={closing || closePreview.running_collection_runs > 0} onClick={() => void confirmSelectedCycleClose()}>
                {closing ? "Fechando…" : `Fechar período e arquivar ${closePreview.archive.to_archive.toLocaleString("pt-BR")}`}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
