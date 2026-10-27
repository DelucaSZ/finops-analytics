"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Clock3 } from "lucide-react";
import { ProviderBadge, Section, StatusIndicator } from "@/components/aven";
import { Alert } from "@/components/ui";
import { formatDate } from "@/lib/api";
import {
  buildDashboardApiQuery,
  parseDashboardSearchParams,
  scopedDashboardHref,
} from "@/lib/dashboard-query.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";
import styles from "./dashboard-operational-insights.module.css";

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

function InsightLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link className={styles.link} href={href}>
      <span>{children}</span>
      <ArrowRight {...iconDefaults} aria-hidden="true" />
    </Link>
  );
}

function CollectionFailureRow({ item }: { item: CollectionFailure }) {
  const accountLabel = item.account_name || item.account_id;
  return (
    <article className={styles.item}>
      <div className={styles.itemHeader}>
        <div className={styles.badges}>
          <ProviderBadge provider={item.provider} />
          <StatusIndicator status="danger" label="Falha" />
        </div>
        <InsightLink href={`/collections/${encodeURIComponent(item.collection_run_id)}`}>
          Ver coleta
        </InsightLink>
      </div>
      <div className={styles.itemCopy}>
        <strong>{accountLabel}</strong>
        <span>Falha em {formatDate(item.started_at)}</span>
        <p>{item.error_summary}</p>
        {item.newer_run?.status === "RUNNING" ? (
          <span className={styles.running}>
            <Clock3 {...iconDefaults} aria-hidden="true" />
            Nova coleta em andamento desde {formatDate(item.newer_run.started_at)}.
          </span>
        ) : null}
      </div>
    </article>
  );
}

export function DashboardOperationalInsights() {
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo(() => parseDashboardSearchParams(searchKey), [searchKey]);
  const apiQuery = useMemo(() => buildDashboardApiQuery(state), [state.accountId, state.provider]);
  const request = useApiQuery<OperationalInsightsResponse>({
    key: queryKeys.dashboard.operationalInsights(state.provider, state.accountId),
    path: `/dashboard/operational-insights${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.insight,
    refetchInterval: INSIGHT_REFRESH_INTERVAL,
  });

  const failures = request.data?.collection_failures;
  if (request.isLoading || request.error || !failures?.count) return null;

  const headline = failures.count === 1
    ? "1 conta apresentou falha na coleta mais recente."
    : `${failures.count} contas apresentaram falha na coleta mais recente.`;
  const collectionsHref = scopedDashboardHref("/collections", state, { status: "FAILED" });

  return (
    <Section
      title="Atenção operacional"
      description={headline}
      actions={failures.count > 1 ? <InsightLink href={collectionsHref}>Ver coletas</InsightLink> : undefined}
      aria-labelledby="dashboard-operational-insight-title"
    >
      <Alert
        variant="warning"
        title="Falhas de coleta"
        description="A Visão Geral preserva os indicadores disponíveis, mas estas contas exigem revisão operacional."
      >
        {failures.count === 1 && failures.items[0] ? (
          <CollectionFailureRow item={failures.items[0]} />
        ) : (
          <details className={styles.details}>
            <summary>
              <span>Ver contas afetadas</span>
              <span>{failures.items.length} exibida(s)</span>
            </summary>
            <div className={styles.list}>
              {failures.items.map((item) => (
                <CollectionFailureRow key={`${item.provider}:${item.account_id}`} item={item} />
              ))}
            </div>
          </details>
        )}
        {failures.truncated ? (
          <p className={styles.truncated}>
            Exibindo {failures.items.length} de {failures.count} contas. Use Coletas para consultar todas.
          </p>
        ) : null}
      </Alert>
    </Section>
  );
}
