"use client";

import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";

type ArchiveFilters = {
  provider?: string;
  account_id?: string;
  region?: string;
  service?: string;
  resource_type?: string;
  status?: string;
  presence_status?: string;
  severity?: string;
  rule?: string;
  collection_run_id?: string;
  resource_id?: string;
  search?: string;
  current?: boolean;
};

type Preview = {
  matched: number;
  to_archive: number;
  already_archived: number;
  by_status: Record<string, number>;
  by_provider: Record<string, number>;
  by_account: Record<string, number>;
  savings: Array<{ currency: string; amount: string | number }>;
  filter_hash: string;
};

type ArchiveResult = {
  archived: number;
  already_archived: number;
  correlation_id: string;
  cycle_closed?: boolean;
  snapshots_created?: number;
  collection_runs?: number;
  failed_collection_runs?: number;
};

type Coverage = {
  total: number;
  success: number;
  failed: number;
  running: number;
};

type Cycle = {
  id: string;
  label: string;
  status: "OPEN" | "CLOSED";
  snapshot_count: number;
  coverage: Coverage;
};

type CycleClosePreview = {
  cycle_id: string;
  label: string;
  snapshots_to_create: number;
  coverage: Coverage;
};

type Props = {
  mode: "individual" | "selected" | "filter" | "period";
  opportunityId?: string;
  opportunityIds?: string[];
  filters?: ArchiveFilters;
  filterLabels?: string[];
  onClose: () => void;
  onSuccess: (message: string) => void;
};

export function OpportunityArchiveDialog({
  mode,
  opportunityId,
  opportunityIds = [],
  filters = {},
  filterLabels = [],
  onClose,
  onSuccess,
}: Props) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [cycle, setCycle] = useState<Cycle | null>(null);
  const [cyclePreview, setCyclePreview] = useState<CycleClosePreview | null>(null);
  const [loading, setLoading] = useState(mode === "filter" || mode === "period");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const archiveAll = useMemo(
    () => !Object.values(filters).some((value) => value !== undefined && value !== "" && value !== false),
    [filters],
  );

  useEffect(() => {
    if (mode !== "filter" && mode !== "period") return;
    let cancelled = false;
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const archivePreviewPromise = api<Preview>("/opportunities/archive-preview", {
          method: "POST",
          body: JSON.stringify({ filters, archive_all: archiveAll }),
        });
        if (mode === "filter") {
          const archivePreview = await archivePreviewPromise;
          if (!cancelled) {
            setPreview(archivePreview);
            setCycle(null);
            setCyclePreview(null);
          }
          return;
        }

        const currentCycle = await api<Cycle>("/opportunity-history/cycles/current");
        const [archivePreview, closePreview] = await Promise.all([
          archivePreviewPromise,
          api<CycleClosePreview>(`/opportunity-history/cycles/${currentCycle.id}/close-preview`),
        ]);
        if (!cancelled) {
          setPreview(archivePreview);
          setCycle(currentCycle);
          setCyclePreview(closePreview);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Não foi possível gerar o preview do arquivamento.",
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [archiveAll, filters, mode]);

  async function confirm() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      if (mode === "individual") {
        if (!opportunityId) throw new Error("Oportunidade não informada.");
        await api(`/opportunities/${opportunityId}/archive`, { method: "POST" });
        onSuccess("Oportunidade arquivada. O status humano e o histórico foram preservados.");
        return;
      }
      if (mode === "selected") {
        const result = await api<ArchiveResult>("/opportunities/bulk/archive", {
          method: "POST",
          body: JSON.stringify({ opportunity_ids: opportunityIds }),
        });
        onSuccess(
          `${result.archived} oportunidade(s) arquivada(s)` +
            (result.already_archived
              ? `. ${result.already_archived} já estava(m) no Histórico.`
              : "."),
        );
        return;
      }
      if (!preview || preview.to_archive === 0) return;
      if (mode === "period") {
        if (!cycle) throw new Error("Ciclo histórico atual indisponível.");
        const result = await api<ArchiveResult>("/opportunities/period-close", {
          method: "POST",
          body: JSON.stringify({ cycle_id: cycle.id, filters, archive_all: archiveAll }),
        });
        onSuccess(
          `Período ${cycle.label} fechado com ${result.snapshots_created ?? 0} snapshots e ${result.archived} oportunidade(s) arquivada(s).`,
        );
        return;
      }
      const result = await api<ArchiveResult>("/opportunities/archive-by-filter", {
        method: "POST",
        body: JSON.stringify({ filters, archive_all: archiveAll }),
      });
      onSuccess(
        `${result.archived} oportunidade(s) arquivada(s)` +
          (result.already_archived
            ? `. ${result.already_archived} já estava(m) no Histórico.`
            : "."),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível arquivar as oportunidades.");
    } finally {
      setSaving(false);
    }
  }

  const selectedCount = opportunityIds.length;
  const title =
    mode === "individual"
      ? "Arquivar oportunidade"
      : mode === "selected"
        ? `Arquivar ${selectedCount} oportunidade(s) selecionada(s)`
        : mode === "period"
          ? "Fechar período operacional"
          : archiveAll
            ? "Arquivar todo o backlog"
            : "Arquivar todas deste filtro";
  const periodCoverage = cyclePreview?.coverage ?? cycle?.coverage;
  const blockedByRunning = mode === "period" && Boolean(periodCoverage?.running);
  const disabled =
    saving ||
    loading ||
    ((mode === "filter" || mode === "period") && (!preview || preview.to_archive === 0)) ||
    blockedByRunning;

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <section
        className="decision-dialog opportunity-archive-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="archive-dialog-title"
      >
        <header className="dialog-heading">
          <div>
            <span className="eyebrow">ARQUIVAMENTO OPERACIONAL</span>
            <h2 id="archive-dialog-title">{title}</h2>
          </div>
          <button
            className="icon-button"
            type="button"
            aria-label="Fechar"
            disabled={saving}
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="modal-body">
          {mode === "individual" && (
            <p>
              Arquivar esta oportunidade? Ela será removida do backlog operacional, mas seu status,
              presença técnica e histórico serão preservados.
            </p>
          )}
          {mode === "selected" && (
            <p>
              As {selectedCount} oportunidades selecionadas serão removidas do backlog operacional
              sem alterar as decisões humanas existentes.
            </p>
          )}
          {(mode === "filter" || mode === "period") && loading && (
            <p>Calculando o escopo no servidor…</p>
          )}
          {(mode === "filter" || mode === "period") && preview && (
            <>
              {archiveAll && (
                <div className="alert" role="alert">
                  <strong>Escopo total.</strong> Você está prestes a arquivar todas as oportunidades
                  operacionais ativas do backlog.
                </div>
              )}
              <dl className="detail-grid">
                {mode === "period" && cycle && (
                  <div>
                    <dt>Período</dt>
                    <dd>{cycle.label}</dd>
                  </div>
                )}
                <div>
                  <dt>Correspondentes</dt>
                  <dd>{preview.matched}</dd>
                </div>
                <div>
                  <dt>Serão arquivadas</dt>
                  <dd>{preview.to_archive}</dd>
                </div>
                <div>
                  <dt>Já arquivadas</dt>
                  <dd>{preview.already_archived}</dd>
                </div>
                {mode === "period" && cyclePreview && (
                  <div>
                    <dt>Snapshots a gerar</dt>
                    <dd>{cyclePreview.snapshots_to_create}</dd>
                  </div>
                )}
                {mode === "period" && periodCoverage && (
                  <div>
                    <dt>Coletas no período</dt>
                    <dd>{periodCoverage.total}</dd>
                  </div>
                )}
                {mode === "period" && periodCoverage && (
                  <div>
                    <dt>Falhas finalizadas</dt>
                    <dd>{periodCoverage.failed}</dd>
                  </div>
                )}
              </dl>
              {filterLabels.length > 0 && (
                <div className="active-filter-summary" aria-label="Filtros do arquivamento">
                  {filterLabels.map((label) => (
                    <span key={label}>{label}</span>
                  ))}
                </div>
              )}
              {preview.savings.length > 0 && (
                <p className="muted-copy">
                  Economia potencial no escopo:{" "}
                  {preview.savings
                    .map(
                      (item) =>
                        `${item.currency} ${Number(item.amount).toLocaleString("pt-BR", {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}`,
                    )
                    .join(" · ")}
                </p>
              )}
              <p className="muted-copy">
                O conjunto pode mudar entre o preview e a execução; a resposta final usa a contagem
                efetivamente arquivada.
              </p>
              {preview.to_archive === 0 && (
                <div className="alert">Nenhuma oportunidade ativa corresponde aos filtros atuais.</div>
              )}
              {mode === "period" && periodCoverage && periodCoverage.failed > 0 && (
                <div className="alert">
                  {periodCoverage.failed} coleta(s) falharam neste período. O snapshot refletirá
                  apenas dados efetivamente observados.
                </div>
              )}
              {blockedByRunning && (
                <div className="alert error">
                  Não é possível fechar este período enquanto existem {periodCoverage?.running}{" "}
                  coleta(s) em andamento.
                </div>
              )}
            </>
          )}
          {error && (
            <div className="alert error" role="alert">
              {error}
            </div>
          )}
        </div>

        <footer className="dialog-actions">
          <button className="button ghost" type="button" disabled={saving} onClick={onClose}>
            Cancelar
          </button>
          <button
            className="button primary"
            type="button"
            disabled={disabled}
            onClick={() => void confirm()}
          >
            {saving
              ? "Processando…"
              : mode === "period"
                ? `Fechar período${preview ? ` e arquivar ${preview.to_archive}` : ""}`
                : mode === "filter"
                  ? `Arquivar ${preview?.to_archive ?? 0} oportunidade(s)`
                  : mode === "selected"
                    ? `Arquivar ${selectedCount} oportunidade(s)`
                    : "Arquivar oportunidade"}
          </button>
        </footer>
      </section>
    </div>
  );
}
