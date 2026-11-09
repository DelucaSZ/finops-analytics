"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, type ReactNode } from "react";
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

function InsightLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link className={styles.link} href={href}>
      <span>{children}</span>
      <ArrowRight {...iconDefaults} aria-hidden="true" />
    </Link>
  );
}

function CollectionFailureRow({ item }: { item: CollectionFailure }) {
  const t = useTranslations("dashboard");
  const accountLabel = item.account_name || item.account_id;
  return (
    <article className={styles.item}>
      <div className={styles.itemHeader}>
        <div className={styles.badges}>
          <ProviderBadge provider={item.provider} />
          <StatusIndicator status="danger" label={t("operational.failure")} />
        </div>
        <InsightLink href={`/collections/${encodeURIComponent(item.collection_run_id)}`}>
          {t("operational.viewCollection")}
        </InsightLink>
      </div>
      <div className={styles.itemCopy}>
        <strong>{accountLabel}</strong>
        <span>{t("operational.failedAt", { date: formatDate(item.started_at) })}</span>
        <p>{item.error_summary}</p>
        {item.newer_run?.status === "RUNNING" ? (
          <span className={styles.running}>
            <Clock3 {...iconDefaults} aria-hidden="true" />
            {t("operational.newRun", { date: formatDate(item.newer_run.started_at) })}
          </span>
        ) : null}
      </div>
    </article>
  );
}

export function DashboardOperationalInsights() {
  const t = useTranslations("dashboard");
  const searchParams = useSearchParams();
  const searchKey = searchParams.toString();
  const state = useMemo(() => parseDashboardSearchParams(searchKey), [searchKey]);
  const apiQuery = useMemo(() => buildDashboardApiQuery(state), [state]);
  const request = useApiQuery<OperationalInsightsResponse>({
    key: queryKeys.dashboard.operationalInsights(state.provider, state.accountId),
    path: `/dashboard/operational-insights${apiQuery ? `?${apiQuery}` : ""}`,
    ...cachePolicy.insight,
    refetchInterval: INSIGHT_REFRESH_INTERVAL,
  });

  const failures = request.data?.collection_failures;
  if (request.isLoading || request.error || !failures?.count) return null;

  const headline = t("operational.failureCount", { count: failures.count });
  const collectionsHref = scopedDashboardHref("/collections", state, { status: "FAILED" });

  return (
    <Section
      title={t("operational.title")}
      description={headline}
      actions={failures.count > 1 ? <InsightLink href={collectionsHref}>{t("operational.viewCollections")}</InsightLink> : undefined}
      aria-label={t("operational.title")}
    >
      <Alert
        variant="warning"
        title={t("operational.collectionFailures")}
        description={t("operational.failuresDescription")}
      >
        {failures.count === 1 && failures.items[0] ? (
          <CollectionFailureRow item={failures.items[0]} />
        ) : (
          <details className={styles.details}>
            <summary>
              <span>{t("operational.affectedAccounts")}</span>
              <span>{t("operational.displayed", { count: failures.items.length })}</span>
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
            {t("operational.truncated", { shown: failures.items.length, total: failures.count })}
          </p>
        ) : null}
      </Alert>
    </Section>
  );
}
