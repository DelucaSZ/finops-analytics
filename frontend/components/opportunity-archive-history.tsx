"use client";

import Link from "next/link";
import { Archive } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

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

export function OpportunityArchiveHistory({ opportunityId }: { opportunityId: string }) {
  const locale = useLocale();
  const t = useTranslations("opportunities.archiveHistory");
  const reasonLabels: Record<string,string> = { MANUAL:t("reason.manual"), RETENTION_POLICY:t("reason.retentionPolicy"), REAPPEARED:t("reason.reappeared") };
  const eventDescription = (item: ArchiveHistoryEntry) => {
    if (item.action === "UNARCHIVE" && item.reason === "REAPPEARED") return t("autoUnarchive");
    if (item.action === "UNARCHIVE") return t("manualUnarchive");
    if (item.reason === "RETENTION_POLICY") {const days = typeof item.context.threshold_days === "number" ? item.context.threshold_days : null; return days ? t("retentionDays", {days}) : t("autoRetention");}
    return t("manualArchive");
  };
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
          <h3 id="archive-history-title"><Archive size={18} /> {t("title")}</h3>
          <p>{t("description")}</p>
        </div>
        {history && <span>{t("events", {count: history.total})}</span>}
      </div>

      {request.error && (
        <div className="alert error" role="alert">
          {t("error")}
        </div>
      )}

      {request.isLoading && !history ? (
        <p className="muted-copy">{t("loading")}</p>
      ) : history?.items.length ? (
        <div className="decision-history">
          {history.items.map((item) => (
            <article key={item.id}>
              <div className="decision-marker" />
              <div>
                <strong>{formatDate(item.occurred_at, locale)} · {item.changed_by_name || t("system")}</strong>
                <p>{item.action === "ARCHIVE" ? t("archived") : t("unarchived")}</p>
                <span>{t("reasonLabel")} {reasonLabels[item.reason] || item.reason}</span>
                <span>{eventDescription(item)}</span>
                {item.collection_run_id && (
                  <Link className="collection-link" href={`/collections/${encodeURIComponent(item.collection_run_id)}`}>
                    {t("openCollection")} {item.collection_run_id.slice(0, 8)}
                  </Link>
                )}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-copy">{t("empty")}</p>
      )}
    </section>
  );
}
