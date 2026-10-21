"use client";

import Link from "next/link";
import { Archive } from "lucide-react";

import { formatDate } from "@/lib/api";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type ArchiveHistoryEntry = {
  id: string;
  action: "ARCHIVE" | "UNARCHIVE";
  reason: "MANUAL" | "RETENTION_POLICY" | "REAPPEARED";
  changed_by: string | null;
  changed_by_name: string | null;
  collection_run_id: string | null;
  occurred_at: string;
  context: Record<string, unknown>;
};

type ArchiveHistoryPage = {
  items: ArchiveHistoryEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

const reasonLabels: Record<string, string> = {
  MANUAL: "Manual",
  RETENTION_POLICY: "Política de retenção",
  REAPPEARED: "Reaparecimento automático",
};

const operationLabels: Record<string, string> = {
  bulk: "Arquivamento em massa por seleção",
  filter: "Arquivamento por filtro",
  period_close: "Fechamento operacional do período",
};

function eventDescription(item: ArchiveHistoryEntry) {
  if (item.action === "UNARCHIVE" && item.reason === "REAPPEARED") {
    return "Desarquivada automaticamente porque a condição voltou a ser observada.";
  }
  if (item.action === "UNARCHIVE") return "Desarquivada manualmente.";
  if (item.reason === "RETENTION_POLICY") {
    const days = typeof item.context.threshold_days === "number" ? item.context.threshold_days : null;
    return days
      ? `Arquivada automaticamente pela política de retenção após ${days} dias.`
      : "Arquivada automaticamente pela política de retenção.";
  }
  return "Arquivada manualmente.";
}

export function OpportunityArchiveHistory({ opportunityId }: { opportunityId: string }) {
  const request = useApiQuery<ArchiveHistoryPage>({
    key: ["opportunities", "archive-history", opportunityId, { page: 1, page_size: 50 }],
    path: `/opportunities/${opportunityId}/archive-history?page=1&page_size=50`,
    ...cachePolicy.detail,
  });
  const history = request.data ?? null;

  return (
    <section className="detail-section" aria-labelledby="archive-history-title">
      <div className="section-heading-inline">
        <div>
          <h3 id="archive-history-title"><Archive size={18} /> Arquivamento</h3>
          <p>Eventos de entrada e saída do histórico, sem alterar o lifecycle humano ou técnico.</p>
        </div>
        {history && <span>{history.total} evento(s)</span>}
      </div>

      {request.error && (
        <div className="alert error" role="alert">
          O histórico de arquivamento está temporariamente indisponível.
        </div>
      )}

      {request.isLoading && !history ? (
        <p className="muted-copy">Carregando histórico de arquivamento…</p>
      ) : history?.items.length ? (
        <div className="decision-history">
          {history.items.map((item) => {
            const operation = typeof item.context.operation === "string" ? item.context.operation : "";
            const correlation = typeof item.context.correlation_id === "string" ? item.context.correlation_id : "";
            return (
              <article key={item.id}>
                <div className="decision-marker" />
                <div>
                  <strong>{formatDate(item.occurred_at)} · {item.changed_by_name || "Sistema"}</strong>
                  <p>{item.action === "ARCHIVE" ? "Arquivada" : "Desarquivada"}</p>
                  <span>Motivo: {reasonLabels[item.reason] || item.reason}</span>
                  <span>{eventDescription(item)}</span>
                  {operation && <span>Operação: {operationLabels[operation] || operation}</span>}
                  {correlation && <span>Correlação: <code>{correlation.slice(0, 12)}</code></span>}
                  {item.collection_run_id && (
                    <Link className="collection-link" href={`/collections/${encodeURIComponent(item.collection_run_id)}`}>
                      Abrir coleta {item.collection_run_id.slice(0, 8)}
                    </Link>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="muted-copy">Nenhum evento de arquivamento registrado.</p>
      )}
    </section>
  );
}
