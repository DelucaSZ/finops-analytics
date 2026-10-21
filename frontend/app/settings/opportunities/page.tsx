"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Check, Eye, Save } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api, ApiError, formatDate } from "@/lib/api";
import styles from "./page.module.css";

type CycleMode = "CALENDAR_MONTH" | "FIXED_DAYS";

type CycleSummary = {
  id: string;
  label: string;
  period_start: string;
  period_end: string;
  status: string;
  timezone: string;
  policy_version: number | null;
};

type Maintenance = {
  last_retention_run_at: string | null;
  last_cycle_close_check_at: string | null;
  last_observation_cleanup_at: string | null;
};

type OpportunityPolicy = {
  id: string;
  cycle_mode: CycleMode;
  cycle_length_days: number;
  cycle_timezone: string;
  cycle_anchor_date: string | null;
  automatic_cycle_close_enabled: boolean;
  treated_archive_enabled: boolean;
  treated_archive_days: number;
  rejected_archive_enabled: boolean;
  rejected_archive_days: number;
  resolved_external_archive_enabled: boolean;
  resolved_external_archive_days: number;
  open_archive_enabled: boolean;
  open_archive_days: number;
  observation_retention_days: number;
  enabled: boolean;
  version: number;
  updated_at: string;
  updated_by: string | null;
  current_cycle: CycleSummary | null;
  next_cycle_start: string | null;
  maintenance: Maintenance;
};

type Preview = {
  treated_eligible: number;
  rejected_eligible: number;
  resolved_externally_eligible: number;
  open_eligible: number;
  observations_eligible_for_purge: number;
  overdue_cycles_awaiting_close: number;
  current_cycle: CycleSummary | null;
  warnings: string[];
};

function editable(policy: OpportunityPolicy) {
  return {
    cycle_mode: policy.cycle_mode,
    cycle_length_days: policy.cycle_length_days,
    cycle_timezone: policy.cycle_timezone,
    cycle_anchor_date: policy.cycle_anchor_date,
    automatic_cycle_close_enabled: policy.automatic_cycle_close_enabled,
    treated_archive_enabled: policy.treated_archive_enabled,
    treated_archive_days: policy.treated_archive_days,
    rejected_archive_enabled: policy.rejected_archive_enabled,
    rejected_archive_days: policy.rejected_archive_days,
    resolved_external_archive_enabled: policy.resolved_external_archive_enabled,
    resolved_external_archive_days: policy.resolved_external_archive_days,
    open_archive_enabled: policy.open_archive_enabled,
    open_archive_days: policy.open_archive_days,
    observation_retention_days: policy.observation_retention_days,
    enabled: policy.enabled,
  };
}

export default function OpportunityPolicyPage() {
  const [policy, setPolicy] = useState<OpportunityPolicy | null>(null);
  const [initial, setInitial] = useState<OpportunityPolicy | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    api<OpportunityPolicy>("/settings/opportunity-policy")
      .then((data) => {
        if (!active) return;
        setPolicy(data);
        setInitial(data);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar a política.");
      });
    return () => { active = false; };
  }, []);

  const reductionWarning = useMemo(() => {
    if (!policy || !initial) return false;
    return (
      policy.observation_retention_days < initial.observation_retention_days ||
      policy.treated_archive_days < initial.treated_archive_days ||
      policy.rejected_archive_days < initial.rejected_archive_days ||
      policy.resolved_external_archive_days < initial.resolved_external_archive_days ||
      (policy.open_archive_enabled && policy.open_archive_days < initial.open_archive_days)
    );
  }, [policy, initial]);

  function patch(changes: Partial<OpportunityPolicy>) {
    setPolicy((current) => current ? { ...current, ...changes } : current);
    setPreview(null);
    setMessage("");
  }

  async function runPreview() {
    if (!policy) return;
    setBusy(true);
    setError("");
    try {
      setPreview(
        await api<Preview>("/settings/opportunity-policy/preview", {
          method: "POST",
          body: JSON.stringify(editable(policy)),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao calcular o impacto.");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!policy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await api<OpportunityPolicy>("/settings/opportunity-policy", {
        method: "PUT",
        body: JSON.stringify({ ...editable(policy), expected_version: policy.version }),
      });
      setPolicy(saved);
      setInitial(saved);
      setPreview(null);
      setMessage("Política de oportunidades atualizada.");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          "A configuração foi alterada por outro administrador. Recarregue os valores antes de salvar novamente.",
        );
      } else {
        setError(err instanceof Error ? err.message : "Falha ao salvar a política.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!policy) {
    return (
      <>
        <PageHeader
          eyebrow="CONFIGURAÇÕES · OPORTUNIDADES"
          title="Retenção e histórico"
          description="Carregando política de retenção e rastreabilidade."
        />
        {error && <div className="alert error">{error}</div>}
      </>
    );
  }

  const cycle = policy.current_cycle;

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES · OPORTUNIDADES"
        title="Retenção e histórico"
        description="Defina quando oportunidades saem do backlog, como os ciclos históricos são fechados e por quanto tempo os detalhes técnicos permanecem disponíveis."
      />

      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert success"><Check size={17} />{message}</div>}

      <section className={styles.statusGrid}>
        <div className="panel">
          <span className={styles.kicker}>VERSÃO</span>
          <strong>{policy.version}</strong>
          <small>Atualizada em {formatDate(policy.updated_at)}</small>
        </div>
        <div className="panel">
          <span className={styles.kicker}>CICLO ATUAL</span>
          <strong>{cycle?.label || "Ainda não criado"}</strong>
          <small>
            {cycle
              ? `${formatDate(cycle.period_start)} → ${formatDate(cycle.period_end)}`
              : "Será criado conforme a política vigente."}
          </small>
        </div>
        <div className="panel">
          <span className={styles.kicker}>PRÓXIMO FECHAMENTO</span>
          <strong>{policy.next_cycle_start ? formatDate(policy.next_cycle_start) : "—"}</strong>
          <small>{policy.automatic_cycle_close_enabled ? "Automático" : "Fechamento manual"}</small>
        </div>
      </section>

      <section className={`panel ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <div>
            <h2>Ciclos de rastreabilidade</h2>
            <p>O período atual não é reformatado ao salvar. As novas regras passam a valer no próximo ciclo.</p>
          </div>
          <label className="switch">
            <input
              aria-label="Habilitar fechamento automático"
              type="checkbox"
              checked={policy.automatic_cycle_close_enabled}
              onChange={(event) => patch({ automatic_cycle_close_enabled: event.target.checked })}
            />
            <span />
          </label>
        </div>

        <div className={styles.formGrid}>
          <label>
            <span>Tipo de ciclo</span>
            <select
              value={policy.cycle_mode}
              onChange={(event) => patch({ cycle_mode: event.target.value as CycleMode })}
            >
              <option value="CALENDAR_MONTH">Mês calendário</option>
              <option value="FIXED_DAYS">Período fixo</option>
            </select>
          </label>
          <label>
            <span>Timezone</span>
            <input
              value={policy.cycle_timezone}
              list="cycle-timezones"
              onChange={(event) => patch({ cycle_timezone: event.target.value })}
            />
            <datalist id="cycle-timezones">
              <option value="UTC" />
              <option value="America/Sao_Paulo" />
            </datalist>
          </label>
          {policy.cycle_mode === "FIXED_DAYS" && (
            <>
              <label>
                <span>Duração do ciclo (dias)</span>
                <input
                  type="number"
                  min={7}
                  max={365}
                  value={policy.cycle_length_days}
                  onChange={(event) => patch({ cycle_length_days: Number(event.target.value) })}
                />
              </label>
              <label>
                <span>Data âncora</span>
                <input
                  type="date"
                  value={policy.cycle_anchor_date || ""}
                  onChange={(event) => patch({ cycle_anchor_date: event.target.value || null })}
                />
              </label>
            </>
          )}
        </div>

        {cycle && (
          <div className={styles.infoBox}>
            O período atual permanece de <strong>{formatDate(cycle.period_start)}</strong> até{" "}
            <strong>{formatDate(cycle.period_end)}</strong>. Alterações de tipo ou timezone serão
            aplicadas somente aos próximos ciclos.
          </div>
        )}
      </section>

      <section className={`panel ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <div>
            <h2>Arquivamento automático</h2>
            <p>Arquivar move a oportunidade para o Histórico sem alterar o status humano.</p>
          </div>
          <label className="switch">
            <input
              aria-label="Habilitar automações da política"
              type="checkbox"
              checked={policy.enabled}
              onChange={(event) => patch({ enabled: event.target.checked })}
            />
            <span />
          </label>
        </div>

        <div className={styles.retentionTable}>
          <RetentionRow
            label="Tratadas"
            detail="Conta a partir da data de tratamento."
            enabled={policy.treated_archive_enabled}
            days={policy.treated_archive_days}
            onEnabled={(value) => patch({ treated_archive_enabled: value })}
            onDays={(value) => patch({ treated_archive_days: value })}
          />
          <RetentionRow
            label="Rejeitadas"
            detail="Conta a partir da data de rejeição; novas detecções continuam suprimidas."
            enabled={policy.rejected_archive_enabled}
            days={policy.rejected_archive_days}
            onEnabled={(value) => patch({ rejected_archive_enabled: value })}
            onDays={(value) => patch({ rejected_archive_days: value })}
          />
          <RetentionRow
            label="Resolvidas externamente"
            detail="Conta a partir da detecção da resolução externa."
            enabled={policy.resolved_external_archive_enabled}
            days={policy.resolved_external_archive_days}
            onEnabled={(value) => patch({ resolved_external_archive_enabled: value })}
            onDays={(value) => patch({ resolved_external_archive_days: value })}
          />
          <RetentionRow
            label="Abertas"
            detail="Opcional: arquiva após X dias sem nova observação, usando a última detecção."
            enabled={policy.open_archive_enabled}
            days={policy.open_archive_days}
            onEnabled={(value) => patch({ open_archive_enabled: value })}
            onDays={(value) => patch({ open_archive_days: value })}
          />
        </div>
      </section>

      <section className={`panel ${styles.section}`}>
        <h2>Detalhes das observações</h2>
        <div className={styles.formGrid}>
          <label>
            <span>Manter detalhes das observações por</span>
            <div className={styles.inlineInput}>
              <input
                type="number"
                min={policy.cycle_mode === "CALENDAR_MONTH" ? 31 : Math.max(30, policy.cycle_length_days)}
                max={3650}
                value={policy.observation_retention_days}
                onChange={(event) => patch({ observation_retention_days: Number(event.target.value) })}
              />
              <span>dias</span>
            </div>
          </label>
        </div>
        <p className={styles.muted}>
          Snapshots de ciclos fechados permanecem disponíveis mesmo depois da remoção das observações detalhadas.
        </p>
      </section>

      {reductionWarning && (
        <div className={`alert warning ${styles.warning}`}>
          <AlertTriangle size={18} />
          Esta alteração reduz retenção. Registros antigos poderão ficar elegíveis para arquivamento
          ou remoção na próxima execução. Nenhum snapshot de ciclo fechado será apagado ao salvar.
        </div>
      )}

      <section className={`panel ${styles.section}`}>
        <div className={styles.actions}>
          <button className="button ghost" onClick={() => void runPreview()} disabled={busy}>
            <Eye size={16} /> Visualizar impacto
          </button>
          <button className="button primary" onClick={() => void save()} disabled={busy}>
            <Save size={16} /> {busy ? "Processando…" : "Salvar política"}
          </button>
        </div>

        {preview && (
          <div className={styles.preview}>
            <h3>Impacto estimado</h3>
            <div className={styles.previewGrid}>
              <Metric label="Tratadas elegíveis" value={preview.treated_eligible} />
              <Metric label="Rejeitadas elegíveis" value={preview.rejected_eligible} />
              <Metric label="Resolvidas elegíveis" value={preview.resolved_externally_eligible} />
              <Metric label="Abertas elegíveis" value={preview.open_eligible} />
              <Metric label="Observações elegíveis para limpeza" value={preview.observations_eligible_for_purge} />
              <Metric label="Ciclos vencidos aguardando fechamento" value={preview.overdue_cycles_awaiting_close} />
            </div>
            {preview.warnings.map((warning) => (
              <p key={warning} className={styles.previewWarning}>{warning}</p>
            ))}
          </div>
        )}
      </section>

      <section className={`panel ${styles.section}`}>
        <h2>Últimas execuções</h2>
        <div className={styles.maintenanceGrid}>
          <span>Retenção <strong>{formatDate(policy.maintenance.last_retention_run_at)}</strong></span>
          <span>Fechamento automático <strong>{formatDate(policy.maintenance.last_cycle_close_check_at)}</strong></span>
          <span>Limpeza de observações <strong>{formatDate(policy.maintenance.last_observation_cleanup_at)}</strong></span>
        </div>
      </section>
    </>
  );
}

function RetentionRow({
  label,
  detail,
  enabled,
  days,
  onEnabled,
  onDays,
}: {
  label: string;
  detail: string;
  enabled: boolean;
  days: number;
  onEnabled: (value: boolean) => void;
  onDays: (value: number) => void;
}) {
  return (
    <div className={styles.retentionRow}>
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <label className="switch">
        <input
          aria-label={`Habilitar arquivamento de ${label}`}
          type="checkbox"
          checked={enabled}
          onChange={(event) => onEnabled(event.target.checked)}
        />
        <span />
      </label>
      <div className={styles.afterDays}>
        <span>após</span>
        <input
          aria-label={`Dias para ${label}`}
          type="number"
          min={1}
          max={3650}
          value={days}
          disabled={!enabled}
          onChange={(event) => onDays(Number(event.target.value))}
        />
        <span>dias</span>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.metric}>
      <strong>{value.toLocaleString("pt-BR")}</strong>
      <span>{label}</span>
    </div>
  );
}
