"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo } from "react";
import { ArrowRight, ChevronLeft, ChevronRight, GitCompareArrows } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge, statusLabel } from "@/components/status-badge";
import { formatDate } from "@/lib/api";
import { formatAccountLabel, formatMoney, providerLabel } from "@/lib/cloud.mjs";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { prefetchApiQuery, useApiQuery } from "@/lib/server-state";
import type {
  CollectionComparisonCategory,
  CollectionComparisonChange,
  CollectionComparisonResponse,
  CollectionComparisonRun,
} from "@/lib/types";
import styles from "../../collection.module.css";

const categories: Array<{
  value: CollectionComparisonCategory;
  labelKey: "new" | "persistent" | "noLonger" | "changed";
  summaryKey: "new" | "persistent" | "no_longer_detected" | "changed";
}> = [
  { value: "NEW", labelKey: "new", summaryKey: "new" },
  { value: "PERSISTENT", labelKey: "persistent", summaryKey: "persistent" },
  {
    value: "NO_LONGER_DETECTED",
    labelKey: "noLonger",
    summaryKey: "no_longer_detected",
  },
  { value: "CHANGED", labelKey: "changed", summaryKey: "changed" },
];

const categoryValues = new Set(categories.map((item) => item.value));

function signedMoney(value: number | string, currency: string, perMonth: string, locale: string) {
  const number = Number(value);
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatMoney(value, currency, locale)}${perMonth}`;
}

function displayValue(value: unknown, locale: string, format: {perMonth: string;structured: (count:number)=>string;empty:string;changed:string}, unit?: string | null): string {
  if (value === null || value === undefined) return "—";
  const currencyUnit = unit?.match(/^([A-Z]{3})_MONTH$/);
  if (currencyUnit && (typeof value === "number" || typeof value === "string")) {
    return `${formatMoney(value, currencyUnit[1], locale)}${format.perMonth}`;
  }
  if (typeof value === "number") {
    const rendered = value.toLocaleString(locale, { maximumFractionDigits: 2 });
    return unit ? `${rendered} ${unit}` : rendered;
  }
  if (typeof value === "string" || typeof value === "boolean") {
    return `${String(value)}${unit ? ` ${unit}` : ""}`;
  }
  if (Array.isArray(value)) {
    const primitives = value.filter(
      (item) => ["string", "number", "boolean"].includes(typeof item),
    );
    return primitives.length === value.length
      ? primitives.join(", ")
      : format.structured(value.length);
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if ("threshold_value" in record) {
      return [record.operator, record.threshold_value, record.unit]
        .filter((item) => item !== null && item !== undefined && item !== "")
        .join(" ");
    }
    const entries = Object.entries(record).slice(0, 4);
    if (!entries.length) return format.empty;
    return entries
      .map(([key, item]) => {
        const simple =
          item === null || ["string", "number", "boolean"].includes(typeof item)
            ? String(item ?? "—")
            : format.changed;
        return `${key}: ${simple}`;
      })
      .join(" · ");
  }
  return String(value);
}

function changeLabel(change: CollectionComparisonChange, labels: {severity:string; threshold:string; parameters:string; confidence:string}) {
  if (change.type === "severity") return labels.severity;
  if (change.type === "financial_impact") return change.label;
  if (change.type === "threshold") return `${labels.threshold} · ${change.label}`;
  if (change.type === "parameters") return labels.parameters;
  if (change.type === "confidence") return labels.confidence;
  return change.label;
}

export default function CollectionComparisonPage() {
  const t = useTranslations("collections.compare");
  return (
    <Suspense fallback={<div className={styles.state}>{t("comparing")}</div>}>
      <CollectionComparisonContent />
    </Suspense>
  );
}

function CollectionComparisonContent() {
  const t = useTranslations("collections.compare");
  const locale = useLocale();
  const valueFormat = {perMonth: t("perMonth"), structured: (count:number) => t("structuredItems", {count}), empty: t("noValues"), changed: t("structureChanged")};
  const params = useParams<{ collectionId: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const collectionId = params.collectionId;
  const searchKey = searchParams.toString();

  const category = useMemo<CollectionComparisonCategory>(() => {
    const requested = searchParams.get("category") as CollectionComparisonCategory | null;
    return requested && categoryValues.has(requested) ? requested : "NEW";
  }, [searchKey, searchParams]);
  const page = useMemo(() => {
    const requested = Number.parseInt(searchParams.get("page") || "1", 10);
    return Number.isInteger(requested) && requested > 0 ? requested : 1;
  }, [searchKey, searchParams]);
  const baselineId = searchParams.get("baseline_id") || "";

  const comparisonQuery = useMemo(() => {
    const query = new URLSearchParams({
      category,
      page: String(page),
      page_size: "50",
    });
    if (baselineId) query.set("baseline_id", baselineId);
    return query.toString();
  }, [baselineId, category, page]);

  const comparisonRequest = useApiQuery<CollectionComparisonResponse>({
    key: queryKeys.collections.comparison(
      collectionId,
      baselineId,
      category,
      page,
      50,
    ),
    path: `/collections/${collectionId}/compare?${comparisonQuery}`,
    ...cachePolicy.comparison,
    keepPreviousData: true,
    placeholderIdentity: `${collectionId}:${baselineId}:${category}`,
  });
  const optionsRequest = useApiQuery<CollectionComparisonRun[]>({
    key: queryKeys.collections.comparisonOptions(collectionId),
    path: `/collections/${collectionId}/comparison-options?limit=100`,
    ...cachePolicy.metadata,
  });

  const comparison = comparisonRequest.data ?? null;
  const options = optionsRequest.data ?? [];
  const loading = comparisonRequest.isLoading;
  const error = comparisonRequest.error?.message || "";

  const updateUrl = useCallback(
    (patch: Record<string, string | number | null>) => {
      const next = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === null || value === "") next.delete(key);
        else next.set(key, String(value));
      }
      router.push(`/collections/${collectionId}/compare?${next.toString()}`);
    },
    [collectionId, router, searchParams],
  );

  useEffect(() => {
    if (baselineId || !comparison?.baseline?.id) return;
    const next = new URLSearchParams(searchParams.toString());
    next.set("baseline_id", comparison.baseline.id);
    next.set("category", category);
    next.set("page", String(page));
    router.replace(`/collections/${collectionId}/compare?${next.toString()}`);
  }, [
    baselineId,
    category,
    collectionId,
    comparison?.baseline?.id,
    page,
    router,
    searchParams,
  ]);

  useEffect(() => {
    if (!comparison || comparison.page >= comparison.total_pages) return;
    const nextPage = comparison.page + 1;
    const query = new URLSearchParams({
      category,
      page: String(nextPage),
      page_size: "50",
    });
    if (baselineId) query.set("baseline_id", baselineId);
    void prefetchApiQuery<CollectionComparisonResponse>({
      key: queryKeys.collections.comparison(
        collectionId,
        baselineId,
        category,
        nextPage,
        50,
      ),
      path: `/collections/${collectionId}/compare?${query.toString()}`,
      ...cachePolicy.comparison,
    }).catch(() => undefined);
  }, [
    baselineId,
    category,
    collectionId,
    comparison,
  ]);

  if (loading && !comparison) {
    return <div className={styles.state}>{t("comparing")}</div>;
  }

  if (error && !comparison) {
    return (
      <div className={styles.state} role="alert">
        {error}
      </div>
    );
  }

  if (!comparison) return null;

  const selectedBaseline = comparison.baseline;
  const summary = comparison.summary;
  const selectedCategory = categories.find((item) => item.value === category) ?? categories[0];
  const categoryLabel = t(selectedCategory.labelKey);
  const financial = comparison.financial_summary;

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <div className={styles.headerActions}>
            <Link className="button ghost" href={`/collections/${comparison.target.id}`}>
              {t("openCurrent")}
            </Link>
            <Link className="button ghost" href="/scans">
              {t("runs")}
            </Link>
          </div>
        }
      />

      {error && <div className="alert error">{error}</div>}
      {optionsRequest.error && comparison && (
        <div className="alert">
          {t("optionsError")}
        </div>
      )}
      {comparisonRequest.isFetching && comparison && (
        <div className="table-loading-bar" role="status">
          <span /> {t("updating")}
        </div>
      )}

      <section className={`panel ${styles.compareHeader}`}>
        <div className={styles.runSide}>
          <span className="eyebrow">{t("previous")}</span>
          {selectedBaseline ? (
            <>
              <Link href={`/collections/${selectedBaseline.id}`}>
                {formatDate(selectedBaseline.started_at, locale)}
              </Link>
              <strong>
                {formatAccountLabel(providerLabel(selectedBaseline.provider), selectedBaseline.account_id)}
              </strong>
              <span>Rules {selectedBaseline.rules_version || t("notRecorded")}</span>
            </>
          ) : (
            <strong>{t("missingBaseline")}</strong>
          )}
        </div>
        <GitCompareArrows size={25} />
        <div className={styles.runSide}>
          <span className="eyebrow">{t("current")}</span>
          <Link href={`/collections/${comparison.target.id}`}>
            {formatDate(comparison.target.started_at, locale)}
          </Link>
          <strong>
            {formatAccountLabel(providerLabel(comparison.target.provider), comparison.target.account_id)}
          </strong>
          <span>Rules {comparison.target.rules_version || t("notRecorded")}</span>
        </div>
        <label className={styles.baselinePicker}>
          {t("compareWith")}
          <select
            value={selectedBaseline?.id || ""}
            disabled={!options.length}
            onChange={(event) =>
              updateUrl({ baseline_id: event.target.value || null, page: 1 })
            }
          >
            {!options.length && <option value="">{t("noCompatible")}</option>}
            {options.map((option) => (
              <option value={option.id} key={option.id}>
                {formatDate(option.started_at, locale)} · {statusLabel(option.status)} · Rules{" "}
                {option.rules_version || "n/d"}
                {!option.detailed_observations_available ? t("expiredDetail") : ""}
              </option>
            ))}
          </select>
        </label>
      </section>

      {!comparison.available && (
        <div className={`alert ${styles.notice}`}>
          {comparison.message ||
            t("noPreviousCompatible")}
        </div>
      )}

      {comparison.rules_version_warning && (
        <div className={`alert ${styles.notice}`}>
          <strong>{t("rulesVersionContext")}</strong>{" "}
          {comparison.rules_version_warning.message}
        </div>
      )}

      {comparison.warnings.map((warning) => (
        <div className={`alert ${styles.notice}`} key={warning.code}>
          <strong>{warning.code === "SCOPE_METADATA_UNAVAILABLE" ? t("scopeWarning") : t("warning")}</strong>{" "}
          {warning.message}
        </div>
      ))}

      {summary && (
        <section className={styles.summaryCards} aria-label={t("summaryAria")}>
          {categories.map((item) => (
            <button
              type="button"
              key={item.value}
              className={`${styles.summaryCard} ${
                category === item.value ? styles.summaryCardActive : ""
              }`}
              onClick={() => updateUrl({ category: item.value, page: 1 })}
            >
              <span>{t(item.labelKey)}</span>
              <strong>{summary[item.summaryKey]}</strong>
            </button>
          ))}
        </section>
      )}

      {financial && (
        <section className={styles.financialGrid}>
          <article>
            <span>{t("baselineImpact")}</span>
            <strong>{formatMoney(financial.baseline_total, financial.currency, locale)}{t("perMonth")}</strong>
          </article>
          <article>
            <span>{t("currentImpact")}</span>
            <strong>{formatMoney(financial.target_total, financial.currency, locale)}{t("perMonth")}</strong>
          </article>
          <article>
            <span>{t("delta")}</span>
            <strong>{signedMoney(financial.delta, financial.currency, t("perMonth"), locale)}</strong>
            {financial.delta_percent !== null && (
              <small>
                {Number(financial.delta_percent) > 0 ? "+" : ""}
                {Number(financial.delta_percent).toLocaleString(locale, {
                  maximumFractionDigits: 1,
                })}
                %
              </small>
            )}
          </article>
          <p>
            {t("metricSummary", {label: financial.label, metric: financial.metric, currency: financial.currency, period: t("perMonth")})}
          </p>
        </section>
      )}

      {comparison.available && summary && (
        <section className={`panel table-panel ${styles.resultsPanel}`}>
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{t("detailPage")}</span>
              <h2>{categoryLabel}</h2>
              <p>
                {t("categoryCount", {count:comparison.total, page: comparison.total_pages ? comparison.page : 0, total:comparison.total_pages})}
              </p>
            </div>
          </div>

          <div className="data-table-wrap" role="region" aria-label={categoryLabel}>
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">{t("opportunity")}</th>
                  <th scope="col">{t("context")}</th>
                  <th scope="col">{t("baseline")}</th>
                  <th scope="col">{t("actual")}</th>
                  <th scope="col">{t("lifecycle")}</th>
                  <th scope="col">{t("changes")}</th>
                  <th scope="col">{t("action")}</th>
                </tr>
              </thead>
              <tbody>
                {comparison.items.map((item) => (
                  <tr key={item.opportunity_id}>
                    <td>
                      <strong>{item.title}</strong>
                      <span>{item.rule_key}</span>
                      <span>{item.resource_name || item.resource_id}</span>
                    </td>
                    <td>
                      <strong>
                        {item.service} · {item.region || t("withoutRegion")}
                      </strong>
                      <span>{item.resource_id}</span>
                      {item.resource_type && <span>{item.resource_type}</span>}
                    </td>
                    <td>
                      {item.baseline ? (
                        <>
                          <StatusBadge value={item.baseline.severity} />
                          <span>{formatMoney(item.baseline.estimated_monthly_savings, item.baseline.currency, locale)}/mês</span>
                          <span>{item.baseline.evidence_summary || t("noSummary")}</span>
                        </>
                      ) : (
                        <span>{t("notObserved")}</span>
                      )}
                    </td>
                    <td>
                      {item.target ? (
                        <>
                          <StatusBadge value={item.target.severity} />
                          <span>{formatMoney(item.target.estimated_monthly_savings, item.target.currency, locale)}/mês</span>
                          <span>{item.target.evidence_summary || t("noSummary")}</span>
                        </>
                      ) : (
                        <span>{t("notDetectedNow")}</span>
                      )}
                    </td>
                    <td>
                      <StatusBadge value={item.lifecycle_status} />
                    </td>
                    <td>
                      {item.changes.length ? (
                        <div className={styles.changeList}>
                          {item.changes.map((change, index) => (
                            <div
                              className={styles.change}
                              key={`${change.type}-${change.label}-${index}`}
                            >
                              <strong>{changeLabel(change, {severity:t("severity"),threshold:t("threshold"),parameters:t("parameters"),confidence:t("confidence")})}</strong>
                              <span>
                                {displayValue(change.baseline, locale, valueFormat, change.unit)}
                                <ArrowRight size={13} />
                                {displayValue(change.target, locale, valueFormat, change.unit)}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <span>
                          {item.category === "PERSISTENT"
                            ? t("detectedBoth")
                            : t("noAttributeDiff")}
                        </span>
                      )}
                    </td>
                    <td>
                      <Link
                        onMouseEnter={() => {
                          void prefetchApiQuery({
                            key: queryKeys.opportunities.detail(item.opportunity_id),
                            path: `/opportunities/${item.opportunity_id}`,
                            ...cachePolicy.detail,
                          }).catch(() => undefined);
                        }}
                        href={`/opportunities?opportunity_id=${encodeURIComponent(
                          item.opportunity_id,
                        )}&comparison_target=${encodeURIComponent(
                          comparison.target.id,
                        )}${
                          selectedBaseline
                            ? `&comparison_baseline=${encodeURIComponent(
                                selectedBaseline.id,
                              )}`
                            : ""
                        }`}
                      >
                        {t("openOpportunity")}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {!comparison.items.length && (
              <div className="empty-table">
                {t("emptyCategory", {category: categoryLabel.toLowerCase()})}
              </div>
            )}
          </div>

          <footer className={styles.pagination}>
            <button
              type="button"
              disabled={comparison.page <= 1}
              onClick={() => updateUrl({ page: comparison.page - 1 })}
            >
              <ChevronLeft size={16} />
              {t("previousPage")}
            </button>
            <span>
              {t("pagination", {page: comparison.total_pages ? comparison.page : 0, total:comparison.total_pages})}
            </span>
            <button
              type="button"
              disabled={
                comparison.total_pages === 0 || comparison.page >= comparison.total_pages
              }
              onClick={() => updateUrl({ page: comparison.page + 1 })}
            >
              {t("nextPage")}
              <ChevronRight size={16} />
            </button>
          </footer>
        </section>
      )}
    </>
  );
}
