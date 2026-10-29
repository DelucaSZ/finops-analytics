"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { History, LockKeyhole, RefreshCw } from "lucide-react";
import { FilterBar, FilterItem } from "@/components/aven";
import { Alert, Button, Input, Select } from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";
import { formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import {
  buildHistorySnapshotQuery,
  chooseHistoryCycle,
  cycleStateLabel,
  historyMoneyRows,
} from "@/lib/opportunity-history.mjs";
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

  async function closeSelectedCycle() {
    if (!cycle || cycle.status !== "OPEN") return;
    setClosing(true);
    setError("");
    try {
      await api(`/opportunity-history/cycles/${cycle.id}/close`, { method: "POST" });
      await loadCycles(cycle.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível fechar o ciclo.");
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
          <Button
            variant="secondary"
            leadingIcon={<RefreshCw {...iconDefaults} />}
            onClick={refresh}
            disabled={loading}
          >
            {loading ? "Atualizando…" : "Atualizar"}
          </Button>
        )}
      />

      <div className={styles.switcher} aria-label="Visões de histórico">
        <span><History {...iconDefaults} /> Ciclos fechados</span>
        <Link href="/opportunities?view=history">Arquivadas atualmente / Histórico legado</Link>
        <Link href="/opportunities">Backlog operacional</Link>
      </div>

      {error && <Alert variant="danger" description={error} />}

      <FilterBar className={styles.filterBar}>
        <FilterItem size="wide">
          <Select
            id="history-cycle"
            label="Período histórico"
            value={cycleId}
            options={cycles.map((item) => ({
              value: item.id,
              label: `${item.label} — ${cycleStateLabel(item.status)}`,
            }))}
            onChange={(event) => { setCycleId(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="compact">
          <Select
            id="history-provider"
            label="Cloud"
            value={provider}
            options={[
              { value: "", label: "Todas" },
              { value: "aws", label: "AWS" },
              { value: "oci", label: "OCI" },
            ]}
            onChange={(event) => { setProvider(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="default">
          <Select
            id="history-status"
            label="Status no fechamento"
            value={status}
            options={[
              { value: "", label: "Todos" },
              { value: "open", label: "Aberta" },
              { value: "treated", label: "Tratada" },
              { value: "rejected", label: "Rejeitada" },
            ]}
            onChange={(event) => { setStatus(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="compact">
          <Select
            id="history-severity"
            label="Severidade"
            value={severity}
            options={[
              { value: "", label: "Todas" },
              { value: "high", label: "Alta" },
              { value: "medium", label: "Média" },
              { value: "low", label: "Baixa" },
            ]}
            onChange={(event) => { setSeverity(event.target.value); setPage(1); }}
          />
        </FilterItem>
        <FilterItem size="wide">
          <Input
            id="history-search"
            label="Buscar no snapshot"
            type="search"
            value={search}
            onChange={(event) => { setSearch(event.target.value); setPage(1); }}
            placeholder="Recurso, título, conta ou ID"
          />
        </FilterItem>
      </FilterBar>

      {cycle && (
        <div className={styles.banner}>
          <strong>{cycle.label} · {cycleStateLabel(cycle.status)}</strong>
          <span className={styles.secondary}>
            {formatDate(cycle.period_start)} até {formatDate(cycle.period_end)} · timezone {cycle.timezone}
            {cycle.closed_at ? ` · fechado em ${formatDate(cycle.closed_at)}` : " · Prévia — período ainda não fechado"}
          </span>
          {cycle.status === "OPEN" && (
            <div className={styles.bannerActions}>
              <Button
                leadingIcon={<LockKeyhole {...iconDefaults} />}
                disabled={closing || cycle.coverage.running > 0}
                onClick={closeSelectedCycle}
              >
                {closing ? "Fechando…" : "Fechar ciclo"}
              </Button>
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
              <Button variant="secondary" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>Anterior</Button>
              <Button variant="secondary" disabled={!snapshots.total_pages || page >= snapshots.total_pages} onClick={() => setPage((value) => value + 1)}>Próxima</Button>
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
            <Button variant="secondary" onClick={() => setSelected(null)}>Fechar detalhe</Button>
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
    </section>
  );
}
