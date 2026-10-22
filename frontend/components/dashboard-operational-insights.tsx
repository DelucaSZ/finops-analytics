"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, ArrowRight, Clock3 } from "lucide-react";
import { formatDate } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import {
  buildDashboardApiQuery,
  parseDashboardSearchParams,
  scopedDashboardHref,
} from "@/lib/dashboard-query.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type NewerRun = {
  id: string;
  status: string;
  started_at: string;
};

type CollectionFailure = {
  provider: string;
  account_id: string;
  account_name: string | null;
  collection_run_id: string;
  started_at: string;
  finished_at: string | null;
  status: "FAILED";
  error_summary: string;
  newer_run: NewerRun | null;
};

type OperationalInsightsResponse = {
  collection_failures: {
    count: number;
    items: CollectionFailure[];
    truncated: boolean;
  };
};

const INSIGHT_REFRESH_INTERVAL = 45_000;

function CollectionFailureRow({ item }: { item: CollectionFailure }) {
  const accountLabel = item.account_name || item.account_id;
  return (
    <article className="dashboard-insight-item">
      <div className="dashboard-insight-item-copy">
        <strong>
          {providerLabel(item.provider)} · {accountLabel}
        </strong>
        <span>Falha em {formatDate(item.started_at)}</span>
        <p>{item.error_summary}</p>
        {item.newer_run?.status === "RUNNING" ? (
          <small className="dashboard-insight-running">
            <Clock3 size={14} aria-hidden="true" />
            Nova coleta em andamento desde {formatDate(item.newer_run.started_at)}.
          </small>
        ) : null}
      </div>
      <Link
        className="button ghost dashboard-insight-run-link"
        href={`/collections/${encodeURIComponent(item.collection_run_id)}`}
        aria-label={`Ver coleta com falha de ${accountLabel}`}
      >
        Ver coleta <ArrowRight size={15} aria-hidden="true" />
      </Link>
    </article>
  );
}

export function DashboardOperationalInsights() {
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo(
    () => parseDashboardSearchParams(searchKey),
    [searchKey],
  );
  const apiQuery = useMemo(
    () => buildDashboardApiQuery(state),
    [state.accountId, state.provider],
  );
  const request = useApiQuery<OperationalInsightsResponse>({
    key: queryKeys.dashboard.operationalInsights(state.provider, state.accountId),
    path: `/dashboard/operational-insights${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.insight,
    refetchInterval: INSIGHT_REFRESH_INTERVAL,
  });

  const failures = request.data?.collection_failures;
  // Insight failure is intentionally isolated from the executive dashboard. Loading,
  // healthy state, or an endpoint error must not create a permanent/false alarm card.
  if (request.isLoading || request.error || !failures?.count) return null;

  const headline =
    failures.count === 1
      ? "1 conta apresentou falha na coleta mais recente."
      : `${failures.count} contas apresentaram falha na coleta mais recente.`;
  const collectionsHref = scopedDashboardHref("/collections", state, {
    status: "FAILED",
  });

  return (
    <section
      className="panel dashboard-operational-insight"
      role="status"
      aria-labelledby="dashboard-operational-insight-title"
    >
      <div className="dashboard-insight-heading">
        <span className="dashboard-insight-icon" aria-hidden="true">
          <AlertTriangle size={20} />
        </span>
        <div>
          <span className="eyebrow">INSIGHTS OPERACIONAIS</span>
          <h2 id="dashboard-operational-insight-title">Falhas de coleta</h2>
          <p>{headline}</p>
        </div>
        {failures.count > 1 ? (
          <Link className="dashboard-insight-all-link" href={collectionsHref}>
            Ver coletas <ArrowRight size={15} aria-hidden="true" />
          </Link>
        ) : null}
      </div>

      {failures.count === 1 && failures.items[0] ? (
        <CollectionFailureRow item={failures.items[0]} />
      ) : (
        <details className="dashboard-insight-details">
          <summary>
            Ver detalhes das contas afetadas
            <span>{failures.items.length} exibida(s)</span>
          </summary>
          <div className="dashboard-insight-list">
            {failures.items.map((item) => (
              <CollectionFailureRow
                key={`${item.provider}:${item.account_id}`}
                item={item}
              />
            ))}
          </div>
        </details>
      )}

      {failures.truncated ? (
        <p className="dashboard-insight-truncated">
          Exibindo {failures.items.length} de {failures.count} contas. Use Coletas para ver todas.
        </p>
      ) : null}
    </section>
  );
}
