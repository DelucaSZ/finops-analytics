"use client";

import Link from "next/link";

import { Activity } from "lucide-react";
import { StatusBadge } from "@/components/status-badge";
import { formatDate } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type PresenceReason =
  | "NOT_OBSERVED_IN_SUCCESSFUL_SCOPE"
  | "MISSING_THRESHOLD_REACHED"
  | "OBSERVED_AGAIN";

type PresenceHistoryEntry = {
  id: string;
  from_status: "active" | "missing" | "resolved_externally";
  to_status: "active" | "missing" | "resolved_externally";
  reason: PresenceReason;
  occurred_at: string;
  missing_count: number;
  missing_threshold: number | null;
  collection_run_id: string | null;
  collection_scope_execution_id: string | null;
  collection_provider: string | null;
  collection_account_id: string | null;
  collection_started_at: string | null;
  scope_region: string | null;
  scope_rule_key: string | null;
  context: Record<string, unknown>;
};

type PresenceHistoryPage = {
  items: PresenceHistoryEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

const reasonLabels: Record<PresenceReason, string> = {
  NOT_OBSERVED_IN_SUCCESSFUL_SCOPE: "Não observada em escopo coletado com sucesso",
  MISSING_THRESHOLD_REACHED: "Limite de ausências válidas atingido",
  OBSERVED_AGAIN: "Condição observada novamente",
};

export function OpportunityPresenceHistory({ opportunityId }: { opportunityId: string }) {
  const request = useApiQuery<PresenceHistoryPage>({
    key: ["opportunities", "presence-history", opportunityId, { page: 1, page_size: 50 }],
    path: `/opportunities/${opportunityId}/presence-history?page=1&page_size=50`,
    ...cachePolicy.detail,
  });

  const history = request.data ?? null;

  return (
    <section className="detail-section" aria-labelledby="presence-history-title">
      <div className="section-heading-inline">
        <div>
          <h3 id="presence-history-title">
            <Activity size={18} /> Presença técnica
          </h3>
          <p>
            Transições automáticas derivadas das coletas, separadas das decisões humanas.
          </p>
        </div>
        {history && <span>{history.total} evento(s)</span>}
      </div>

      {request.error && (
        <div className="alert error" role="alert">
          O histórico de presença técnica está temporariamente indisponível.
        </div>
      )}

      {request.isLoading && !history ? (
        <p className="muted-copy">Carregando histórico de presença…</p>
      ) : history?.items.length ? (
        <div className="decision-history">
          {history.items.map((item) => (
            <article key={item.id}>
              <div className="decision-marker" />
              <div>
                <strong>{formatDate(item.occurred_at)}</strong>
                <p>
                  <StatusBadge value={item.from_status} /> <span aria-hidden="true">→</span>{" "}
                  <StatusBadge value={item.to_status} />
                </p>
                <span>{reasonLabels[item.reason]}</span>
                <span>
                  Ausências válidas: {item.missing_count}
                  {item.missing_threshold !== null
                    ? ` / limite ${item.missing_threshold}`
                    : ""}
                </span>
                {item.scope_rule_key && (
                  <span>
                    Escopo: {item.scope_rule_key}
                    {item.scope_region ? ` · ${item.scope_region}` : ""}
                  </span>
                )}
                {item.collection_provider && item.collection_account_id && (
                  <span>
                    {providerLabel(item.collection_provider)} · {item.collection_account_id}
                  </span>
                )}
                {item.collection_run_id && (
                  <Link
                    className="collection-link"
                    href={`/collections/${encodeURIComponent(item.collection_run_id)}`}
                  >
                    Abrir coleta {item.collection_run_id.slice(0, 8)}
                  </Link>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-copy">Nenhuma transição técnica registrada desde a implantação.</p>
      )}

      {history && history.total_pages > 1 && (
        <p className="muted-copy">
          Exibindo os 50 eventos técnicos mais recentes. A API permite paginação do histórico
          completo.
        </p>
      )}
    </section>
  );
}
