"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { api } from "@/lib/api";
import type { ArchiveScope } from "@/lib/opportunity-archive.mjs";

type MoneyTotal = {
  currency: string;
  current_monthly_cost: string | number;
  estimated_monthly_savings: string | number;
};

export type ArchivePreview = {
  matched: number;
  to_archive: number;
  already_archived: number;
  by_status: Record<string, number>;
  by_provider: Record<string, number>;
  account_count: number;
  currencies: MoneyTotal[];
  filter_hash: string;
  generated_at: string;
  archive_all: boolean;
};

export type ArchiveOperationResult = {
  requested: number;
  matched: number;
  archived: number;
  already_archived: number;
  failed: number;
  correlation_id: string;
  sample_ids: string[];
  ids_truncated: boolean;
  filter_hash?: string | null;
};

type Props = {
  scope: ArchiveScope;
  filterLabels: string[];
  onClose: () => void;
  onSuccess: (result: ArchiveOperationResult) => void;
};

function number(value: number) {
  return value.toLocaleString("pt-BR");
}

export function OpportunityArchiveDialog({ scope, filterLabels, onClose, onSuccess }: Props) {
  const [preview, setPreview] = useState<ArchivePreview | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<ArchivePreview>("/opportunities/archive-preview", {
      method: "POST",
      body: JSON.stringify(scope),
    }).then((data) => {
      if (active) setPreview(data);
    }).catch((reason) => {
      if (active) setError(reason instanceof Error ? reason.message : "Não foi possível calcular o escopo do arquivamento.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [scope]);

  useEffect(() => {
    closeRef.current?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !saving) onClose();
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose, saving]);

  async function confirm() {
    if (!preview?.to_archive || saving) return;
    setSaving(true);
    setError("");
    try {
      const result = await api<ArchiveOperationResult>("/opportunities/archive-by-filter", {
        method: "POST",
        body: JSON.stringify(scope),
      });
      onSuccess(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível arquivar as oportunidades.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget && !saving) onClose();
    }}>
      <section className="decision-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-dialog-title">
        <div className="dialog-heading">
          <div>
            <span className="eyebrow">ARQUIVAMENTO OPERACIONAL</span>
            <h2 id="archive-dialog-title">{scope.archive_all ? "Arquivar todo o backlog" : "Arquivar todas deste filtro"}</h2>
            <p>O status humano e a presença técnica serão preservados. Os itens sairão do backlog atual e continuarão no Histórico.</p>
          </div>
          <button ref={closeRef} className="icon-button" type="button" aria-label="Fechar" disabled={saving} onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {loading && <p role="status">Calculando o escopo no servidor…</p>}
        {!loading && preview && (
          <div className="stack-sm">
            {scope.archive_all ? (
              <p className="dialog-error">Você está prestes a arquivar todas as oportunidades operacionais atualmente ativas.</p>
            ) : (
              <>
                <p><strong>{number(preview.to_archive)}</strong> oportunidades ativas correspondem aos filtros atuais.</p>
                {filterLabels.length > 0 && (
                  <div className="active-filters" aria-label="Filtros do arquivamento">
                    {filterLabels.map((label) => <span className="filter-chip" key={label}>{label}</span>)}
                  </div>
                )}
              </>
            )}
            <p>{number(preview.already_archived)} oportunidades do mesmo escopo já estão no Histórico.</p>
            <p>{preview.account_count} conta(s) · {Object.entries(preview.by_provider).map(([key, value]) => `${key.toUpperCase()}: ${number(value)}`).join(" · ") || "sem resultados"}</p>
            {preview.currencies.length > 0 && (
              <p>Impacto no escopo: {preview.currencies.map((item) => `${item.currency} ${Number(item.estimated_monthly_savings).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/mês`).join(" · ")}</p>
            )}
            {preview.to_archive === 0 && <p>Nenhuma oportunidade ativa corresponde aos filtros atuais.</p>}
          </div>
        )}
        {error && <p className="dialog-error" role="alert">{error}</p>}

        <div className="dialog-actions">
          <button className="button ghost" type="button" disabled={saving} onClick={onClose}>Cancelar</button>
          <button className="button primary" type="button" disabled={saving || loading || !preview?.to_archive} onClick={confirm}>
            {saving ? "Arquivando…" : preview ? `Arquivar ${number(preview.to_archive)} oportunidades` : "Arquivar"}
          </button>
        </div>
      </section>
    </div>
  );
}
