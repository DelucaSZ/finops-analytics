"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Suspense, useMemo } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { formatDate } from "@/lib/api";
import { formatAccountLabel, formatNumber, providerLabel } from "@/lib/cloud.mjs";
import {
  COLLECTION_DISCOVERY_LABELS,
  COLLECTION_DISCOVERY_TYPES,
} from "@/lib/collection-query.mjs";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type DiscoveryType =
  | "observed"
  | "first_seen"
  | "new_vs_previous"
  | "reappeared"
  | "continued"
  | "no_longer_detected";

type RunOpportunity = {
  id: string;
  provider: string;
  account_id: string;
  rule_key: string;
  service: string;
  region: string | null;
  resource_id: string;
  resource_name: string | null;
  resource_type: string | null;
  title: string;
  severity: string;
  status: string;
  presence_status: string;
  first_seen_at: string;
  last_seen_at: string;
  archived_at: string | null;
};

type RunOpportunityPage = {
  collection_run_id: string;
  baseline_run_id: string | null;
  comparable: boolean;
  reason: string | null;
  discovery_type: DiscoveryType;
  items: RunOpportunity[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export default function CollectionOpportunitiesPage() {
  return (
    <Suspense fallback={<p role="status">{t("loading")}</p>}>
      <CollectionOpportunitiesContent />
    </Suspense>
  );
}

function CollectionOpportunitiesContent() {
  const t = useTranslations("opportunities.collection");
  const statusT = useTranslations("opportunities.status");
  const decisionLabel = (value:string) => value === "resolved_externally" ? statusT("resolvedExternally") : ["open","treated","rejected","active","missing"].includes(value) ? statusT(value as "open" | "treated" | "rejected" | "active" | "missing") : value;
  const { collectionId } = useParams<{ collectionId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const requestedType = searchParams.get("discovery_type") || "observed";
  const discoveryType: DiscoveryType = COLLECTION_DISCOVERY_TYPES.some(
    (type) => type === requestedType,
  )
    ? (requestedType as DiscoveryType)
    : "observed";
  const page = Math.max(1, Number(searchParams.get("page") || 1) || 1);
  const provider = searchParams.get("provider") || "";
  const accountId = searchParams.get("account_id") || "";
  const apiQuery = useMemo(() => {
    const params = new URLSearchParams({
      discovery_type: discoveryType,
      include_archived: "true",
      page: String(page),
      page_size: "50",
    });
    return params.toString();
  }, [discoveryType, page]);

  const request = useApiQuery<RunOpportunityPage>({
    key: ["collections", collectionId, "opportunities", discoveryType, page, "all-archive-states"],
    path: `/collections/${encodeURIComponent(collectionId)}/opportunities?${apiQuery}`,
    ...cachePolicy.operational,
    keepPreviousData: true,
  });
  const data = request.data;
  const discoveryLabels: Record<string,string> = { observed:t("discovery.observed"),first_seen:t("discovery.firstSeen"),new_vs_previous:t("discovery.newVsPrevious"),reappeared:t("discovery.reappeared"),continued:t("discovery.continued"),no_longer_detected:t("discovery.noLongerDetected") };
  const label = discoveryLabels[discoveryType] || COLLECTION_DISCOVERY_LABELS[discoveryType] || discoveryType;

  function changePage(next: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("page", String(next));
    router.replace(
      `/opportunities/collection/${encodeURIComponent(collectionId)}?${params.toString()}`,
      { scroll: false },
    );
  }

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={label}
        description={t("description")}
      />
      <div className="collection-toolbar">
        <Link className="button ghost" href={`/collections/${encodeURIComponent(collectionId)}`}>
          ← {t("backCollection")}
        </Link>
        <Link className="button ghost" href="/opportunities">
          Abrir backlog atual
        </Link>
      </div>

      <section className="panel" aria-busy={request.isLoading || request.isFetching}>
        <div className="active-filter-summary" aria-label={t("filtersAria")}>
          <span>{t("collection")} {collectionId.slice(0, 8)}</span>
          <span>{t("classification")} {label}</span>
          {provider && <span>Cloud: {providerLabel(provider)}</span>}
          {accountId && <span>{t("account")} {formatAccountLabel(null, accountId)}</span>}
        </div>
        <p className="collection-note">
          {t("notice")}
        </p>

        {request.error && (
          <div className="alert error" role="alert">
            {t("error")}
            <button className="button ghost" onClick={() => void request.refetch()}>
              {t("retry")}
            </button>
          </div>
        )}
        {(request.isLoading || request.isFetching) && (
          <p role="status">{t("loading")}</p>
        )}
        {data?.reason === "NO_BASELINE" &&
          discoveryType !== "observed" &&
          discoveryType !== "first_seen" && (
            <div className="alert" role="status">
              {t("noBaseline")}
            </div>
          )}
        {(data?.reason === "TARGET_OBSERVATIONS_EXPIRED" ||
          data?.reason === "BASELINE_OBSERVATIONS_EXPIRED") && (
          <div className="alert" role="status">
            {t("retentionExpired")}
          </div>
        )}
        {data?.reason === "TARGET_NOT_SUCCESSFUL" &&
          discoveryType !== "observed" &&
          discoveryType !== "first_seen" && (
            <div className="alert" role="status">
              {t("targetFailed")}
            </div>
          )}

        {data && (
          <div className="panel-heading collection-toolbar">
            <h2>{t("count",{count:data.total})}</h2>
            {data.baseline_run_id && (
              <span>
                {t("baseline")} <code>{data.baseline_run_id.slice(0, 8)}</code>
              </span>
            )}
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="data-table-wrap" tabIndex={0} role="region" aria-label={label}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("table.opportunity")}</th>
                  <th>{t("table.cloudAccount")}</th>
                  <th>{t("table.serviceRegion")}</th>
                  <th>{t("table.currentStatus")}</th>
                  <th>{t("table.firstLast")}</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <Link
                        className="collection-link"
                        href={`/opportunities?opportunity_id=${encodeURIComponent(item.id)}`}
                      >
                        {item.title}
                      </Link>
                      <span>{item.resource_name || item.resource_id}</span>
                      <code>{item.rule_key}</code>
                    </td>
                    <td>
                      {providerLabel(item.provider)}
                      <span>{item.account_id}</span>
                    </td>
                    <td>
                      {item.service}
                      <span>{item.region || t("table.global")}</span>
                    </td>
                    <td>
                      {decisionLabel(item.status)}
                      {item.archived_at ? <span>{t("table.archived")}</span> : null}
                    </td>
                    <td>
                      {formatDate(item.first_seen_at)}
                      <span>{formatDate(item.last_seen_at)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && !request.isLoading && data.items.length === 0 && !data.reason && (
          <div className="empty-table">{t("empty")}</div>
        )}
        {data && (
          <div className="collection-toolbar collection-pagination">
            <span>
              {t("page",{page:data.page,total:data.total_pages || 1})}
            </span>
            <button
              className="button ghost"
              disabled={data.page <= 1}
              onClick={() => changePage(data.page - 1)}
            >
              Anterior
            </button>
            <button
              className="button ghost"
              disabled={data.total_pages === 0 || data.page >= data.total_pages}
              onClick={() => changePage(data.page + 1)}
            >
              Próxima
            </button>
          </div>
        )}
      </section>
    </>
  );
}
