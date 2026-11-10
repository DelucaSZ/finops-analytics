"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { CollectionComparisonActions } from "@/components/collection-comparison-actions";
import { Button, Input, Select } from "@/components/ui";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, CircleAlert, Clock3, RefreshCw } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { ApiError, formatDate } from "@/lib/api";
import { formatAccountLabel, formatNumber, providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { prefetchApiQuery, useApiQuery } from "@/lib/server-state";
import {
  COLLECTION_STATUSES,
  buildCollectionQuery,
  collectionOpportunitiesUrl,
  durationLabel,
  localDateTime,
  parseCollectionQuery,
  patchCollectionQuery,
} from "@/lib/collection-query.mjs";
import type {
  CollectionDetail,
  CollectionItem,
  CollectionOptions,
  CollectionPage,
} from "@/lib/types";

const number = (value: number) => formatNumber(value);
function preciseDate(value: string | null, locale: string) {
  return value ? new Date(value).toLocaleString(locale) : "—";
}

function RunStatus({ run }: { run: CollectionItem }) {
  const t = useTranslations("collections.workspace");
  const Icon =
    run.status === "SUCCESS"
      ? CheckCircle2
      : run.status === "FAILED"
        ? CircleAlert
        : Clock3;
  return (
    <span
      className={`collection-status collection-${run.status.toLowerCase()}`}
    >
      <Icon size={16} aria-hidden="true" />
      {run.status === "SUCCESS" ? t("status.success") : run.status === "FAILED" ? t("status.failed") : run.status === "RUNNING" ? t("status.running") : run.status}
      {run.has_warnings ? t("withWarnings") : ""}
    </span>
  );
}

function RunLink({
  run,
  href,
}: {
  run: CollectionItem | null;
  href: (id: string) => string;
}) {
  const t = useTranslations("collections.workspace");
  return run ? (
    <Link href={href(run.id)}>
      <RunStatus run={run} /> · {formatDate(run.started_at)}
    </Link>
  ) : (
    <span>{t("noneRecorded")}</span>
  );
}

export function CollectionWorkspace({
  collectionId,
}: {
  collectionId?: string;
}) {
  const t = useTranslations("collections.workspace");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams().toString();
  const state = useMemo(() => parseCollectionQuery(search), [search]);
  const query = buildCollectionQuery(state);
  const [draft, setDraft] = useState(state);
  const [validation, setValidation] = useState("");
  const [now, setNow] = useState(Date.now());
  const [optionScope, setOptionScope] = useState({
    provider: state.provider,
    search: state.account_id,
  });

  const listPlaceholderIdentity = useMemo(
    () =>
      buildCollectionQuery({
        ...state,
        page: 1,
      }),
    [search],
  );
  const optionQuery = useMemo(() => {
    const params = new URLSearchParams({ limit: "50" });
    if (optionScope.provider) params.set("provider", optionScope.provider);
    if (optionScope.search) params.set("search", optionScope.search);
    return params.toString();
  }, [optionScope.provider, optionScope.search]);

  const listRequest = useApiQuery<CollectionPage>({
    key: queryKeys.collections.list(query),
    path: `/collections?${query}`,
    enabled: !collectionId,
    ...cachePolicy.operational,
    keepPreviousData: true,
    placeholderIdentity: listPlaceholderIdentity,
  });
  const detailRequest = useApiQuery<CollectionDetail>({
    key: queryKeys.collections.detail(collectionId || ""),
    path: `/collections/${encodeURIComponent(collectionId || "")}`,
    enabled: Boolean(collectionId),
    ...cachePolicy.detail,
  });
  const optionsRequest = useApiQuery<CollectionOptions>({
    key: queryKeys.collections.options(
      optionScope.provider,
      optionScope.search,
      50,
    ),
    path: `/collections/options?${optionQuery}`,
    enabled: !collectionId,
    ...cachePolicy.metadata,
  });

  const data = listRequest.data ?? null;
  const detail = detailRequest.data ?? null;
  const options = optionsRequest.data ?? {
    providers: [],
    accounts: [],
    has_more_accounts: false,
  };
  const optionsError = Boolean(optionsRequest.error);
  const loading = collectionId
    ? detailRequest.isLoading
    : listRequest.isLoading;
  const refreshing = collectionId
    ? detailRequest.isFetching && !detailRequest.isLoading
    : listRequest.isFetching && !listRequest.isLoading;
  const requestError = collectionId ? detailRequest.error : listRequest.error;
  const error = requestError
    ? requestError instanceof ApiError && requestError.status === 404
      ? t("errors.notFound")
      : collectionId
        ? t("errors.detailLoad")
        : t("errors.listLoad")
    : "";

  const hasFilters = Boolean(
    state.provider ||
    state.account_id ||
    state.status ||
    state.date_from ||
    state.date_to ||
    state.analyzer_version,
  );
  const selectedAccount = options.accounts.find(
    (account) => account.account_id === state.account_id && (!state.provider || account.provider === state.provider),
  );
  const activeFilters = [
    state.provider ? t("filterSummary.cloud", {value: providerLabel(state.provider)}) : "",
    state.account_id ? t("filterSummary.account", {value: formatAccountLabel(selectedAccount?.account_name, state.account_id)}) : "",
    state.status ? t("filterSummary.status", {value: state.status === "SUCCESS" ? t("status.success") : state.status === "FAILED" ? t("status.failed") : t("status.running")}) : "",
    state.analyzer_version ? t("filterSummary.version", {value: state.analyzer_version}) : "",
    state.date_from ? t("filterSummary.from", {value: preciseDate(state.date_from, locale)}) : "",
    state.date_to ? t("filterSummary.to", {value: preciseDate(state.date_to, locale)}) : "",
  ].filter(Boolean);
  const detailHref = (id: string) =>
    `/collections/${encodeURIComponent(id)}?${query}`;
  const change = (patch: Record<string, string | number>) =>
    router.push(`${pathname}?${patchCollectionQuery(search, patch)}`, {
      scroll: false,
    });
  useEffect(() => {
    setDraft(state);
    setValidation("");
  }, [state]);

  useEffect(() => {
    if (collectionId) return;
    const timer = window.setTimeout(() => {
      setOptionScope({
        provider: draft.provider,
        search: draft.account_id,
      });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [collectionId, draft.provider, draft.account_id]);

  const hasRunning = collectionId
    ? detail?.status === "RUNNING"
    : Boolean(data?.items.some((run) => run.status === "RUNNING"));

  useEffect(() => {
    if (!hasRunning) return;
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible") return;
      setNow(Date.now());
      if (collectionId) void detailRequest.refetch();
      else void listRequest.refetch();
    }, 15000);
    return () => window.clearInterval(timer);
  }, [collectionId, detailRequest.refetch, hasRunning, listRequest.refetch]);

  const statusOptions = Object.entries(COLLECTION_STATUSES).map(([value]) => ({value, label: value === "SUCCESS" ? t("status.success") : value === "FAILED" ? t("status.failed") : t("status.running")}));
  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={collectionId ? t("collectionIdTitle", {id: collectionId.slice(0, 8)}) : t("title")}
        description={t("description")}
      />
      <div className="collection-toolbar">
        {collectionId && (
          <Link className="button ghost" href={`/collections?${query}`}>
            {t("back")}
          </Link>
        )}
        <span>
          {t("refreshNote")}
        </span>
        <Button
          variant="ghost"
          leadingIcon={<RefreshCw {...iconDefaults} />}
          disabled={loading || refreshing}
          onClick={() => {
            if (collectionId) void detailRequest.refetch();
            else {
              void listRequest.refetch();
              void optionsRequest.refetch();
            }
          }}
        >
          {t("refresh")}
        </Button>
      </div>
      {!collectionId && (
        <form
          className="panel opportunity-filter-panel"
          onSubmit={(event) => {
            event.preventDefault();
            if (
              draft.date_from &&
              draft.date_to &&
              new Date(draft.date_from) >= new Date(draft.date_to)
            ) {
              setValidation("DATE_RANGE_INVALID");
              return;
            }
            setValidation("");
            change({ ...draft, page: 1 });
          }}
        >
          <div className="opportunity-filter-heading">
            <strong>{t("filtersTitle")}</strong>
            {hasFilters && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => router.push("/collections")}
              >
                {t("clearFilters")}
              </Button>
            )}
          </div>
          {activeFilters.length > 0 && (
            <div className="active-filter-summary" aria-label={t("activeFilters")}>
              {activeFilters.map((label) => <span key={label}>{label}</span>)}
            </div>
          )}
          <div className="opportunity-filter-grid">
            <div className="opportunity-filter">
              <Input
                label={t("cloud")}
                list="collection-providers"
                placeholder={t("allClouds")}
                value={draft.provider}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    provider: event.target.value,
                    account_id: "",
                  })
                }
              />
              <datalist id="collection-providers">
                {options.providers.map((provider) => (
                  <option key={provider} value={provider}>
                    {providerLabel(provider)}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="opportunity-filter account-filter">
              <Input
                label={t("accountSearch")}
                list="collection-accounts"
                placeholder={t("accountPlaceholder")}
                value={draft.account_id}
                helperText={options.has_more_accounts ? t("moreAccounts") : undefined}
                onChange={(event) =>
                  setDraft({ ...draft, account_id: event.target.value })
                }
              />
              <datalist id="collection-accounts">
                {options.accounts.map((account) => (
                  <option
                    key={`${account.provider}:${account.account_id}`}
                    value={account.account_id}
                  >
                    {account.account_name || account.account_id} ·{" "}
                    {providerLabel(account.provider)} · {account.account_id}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="opportunity-filter">
              <Select
                label={t("statusLabel")}
                value={draft.status}
                options={[
                  { value: "", label: t("all") },
                  ...statusOptions,
                ]}
                onChange={(event) =>
                  setDraft({ ...draft, status: event.target.value })
                }
              />
            </div>
            <div className="opportunity-filter">
              <Input
                type="datetime-local"
                label={t("periodStart")}
                value={localDateTime(draft.date_from)}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    date_from: event.target.value
                      ? new Date(event.target.value).toISOString()
                      : "",
                  })
                }
              />
            </div>
            <div className="opportunity-filter">
              <Input
                type="datetime-local"
                label={t("periodEnd")}
                value={localDateTime(draft.date_to)}
                onChange={(event) =>
                  setDraft({
                    ...draft,
                    date_to: event.target.value
                      ? new Date(event.target.value).toISOString()
                      : "",
                  })
                }
              />
            </div>
            <div className="opportunity-filter">
              <Input
                label={t("analyzerVersion")}
                placeholder={t("allVersions")}
                value={draft.analyzer_version}
                onChange={(event) =>
                  setDraft({ ...draft, analyzer_version: event.target.value })
                }
              />
            </div>
          </div>
          {optionsError && (
            <p role="status">
              {t("suggestionsError")}
            </p>
          )}
          {validation && (
            <p className="form-error" role="alert">
              {validation === "DATE_RANGE_INVALID" ? t("dateRangeInvalid") : validation}
            </p>
          )}
          <div className="collection-toolbar">
            <Button type="submit">{t("applyFilters")}</Button>
            <Button
              variant="ghost"
              onClick={() => {
                const end = new Date();
                const start = new Date(end);
                start.setDate(start.getDate() - 30);
                change({
                  ...draft,
                  date_from: start.toISOString(),
                  date_to: end.toISOString(),
                  page: 1,
                });
              }}
            >
              {t("last30Days")}
            </Button>
          </div>
        </form>
      )}
      {error && (
        <div className="alert error" role="alert">
          {error}{" "}
          <Button
            variant="ghost"
            onClick={() => {
              if (collectionId) void detailRequest.refetch();
              else void listRequest.refetch();
            }}
          >
            {t("retry")}
          </Button>
        </div>
      )}
      {(loading || refreshing) && (
        <p role="status">
          {loading ? t("loading") : t("updating")}
        </p>
      )}
      {!collectionId && data?.account_summary && (
        <section
          className="panel collection-account-summary"
          aria-label={t("lastAccountRuns")}
        >
          <p>
            {t("accountContext")}
          </p>
          <p>
            <strong>{t("lastRun")} </strong>
            <RunLink run={data.account_summary.latest_run} href={detailHref} />
          </p>
          <p>
            <strong>{t("lastSuccess")} </strong>
            <RunLink
              run={data.account_summary.latest_success}
              href={detailHref}
            />
          </p>
          <small>{t("warningNote")}</small>
        </section>
      )}
      {!collectionId && (
        <section
          className="panel table-panel"
          aria-label={t("history")}
          aria-busy={loading}
        >
          <div className="panel-heading collection-toolbar">
            <h2>{data ? t("count", {count: data.total}) : t("history")}</h2>
            <label>
              {t("sortBy")}{" "}
              <select
                aria-label={t("sortBy")}
                value={state.sort}
                onChange={(event) => change({ sort: event.target.value })}
              >
                <option value="started_at">{t("started")}</option>
                <option value="opportunities_found">
                  {t("opportunitiesFound")}
                </option>
              </select>
            </label>
            <label>
              {t("direction")}{" "}
              <select
                aria-label={t("direction")}
                value={state.order}
                onChange={(event) => change({ order: event.target.value })}
              >
                <option value="desc">{t("descending")}</option>
                <option value="asc">{t("ascending")}</option>
              </select>
            </label>
          </div>
          <div
            className="data-table-wrap"
            tabIndex={0}
            role="region"
            aria-label={t("tableLabel")}
          >
            <table className="data-table collection-table">
              <thead>
                <tr>
                  {[
                    t("columns.period"), t("cloud"), t("account"), t("statusLabel"), t("duration"), t("resources"), t("opportunitiesFound"),
                  ].map((label) => (
                    <th scope="col" key={label}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {!data &&
                  loading &&
                  Array.from({ length: 5 }, (_, row) => (
                    <tr key={row} aria-hidden="true">
                      {Array.from({ length: 7 }, (_, cell) => (
                        <td key={cell}>
                          <span className="skeleton-box skeleton-line" />
                        </td>
                      ))}
                    </tr>
                  ))}
                {data?.items.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link
                        className="collection-link"
                        href={detailHref(run.id)}
                        onMouseEnter={() => {
                          void prefetchApiQuery({
                            key: queryKeys.collections.detail(run.id),
                            path: `/collections/${encodeURIComponent(run.id)}`,
                            ...cachePolicy.detail,
                          }).catch(() => undefined);
                        }}
                      >
                        {formatDate(run.started_at)}
                      </Link>
                      <span>{t("finished")}: {formatDate(run.finished_at)}</span>
                      <code>{run.id.slice(0, 8)}</code>
                    </td>
                    <td>{providerLabel(run.provider)}</td>
                    <td>
                      <strong>{run.account_name || run.account_id}</strong>
                      {run.account_name && <span>{run.account_id}</span>}
                    </td>
                    <td>
                      <RunStatus run={run} />
                    </td>
                    <td>{durationLabel(run, now)}</td>
                    <td>
                      {run.resources_analyzed_available
                        ? number(run.resources_analyzed)
                        : t("unavailable")}
                    </td>
                    <td>
                      {run.status === "RUNNING"
                        ? t("waitingCompletion")
                        : number(run.opportunities_found)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!loading && !error && data && !data.items.length && (
            <div className="empty-table">
              <p>
                {hasFilters
                  ? t("emptyFiltered")
                  : state.page > 1
                    ? t("emptyPage")
                    : t("emptyAll")}
              </p>
              {hasFilters && (
                <Button variant="ghost" onClick={() => router.push("/collections")}>
                  {t("clearFilters")}
                </Button>
              )}
            </div>
          )}
          <div className="collection-toolbar collection-pagination">
            <label>
              {t("perPage")}{" "}
              <select
                aria-label={t("perPage")}
                value={state.page_size}
                onChange={(event) =>
                  change({ page_size: Number(event.target.value) })
                }
              >
                {[25, 50, 100].map((size) => (
                  <option key={size}>{size}</option>
                ))}
              </select>
            </label>
            <span>
              {t("pagination", {page: state.page, total: data?.total_pages || 1})}
            </span>
            <Button
              variant="ghost"
              disabled={loading || state.page <= 1}
              onClick={() => change({ page: state.page - 1 })}
            >
              {t("previous")}
            </Button>
            <Button
              variant="ghost"
              disabled={loading || !data || state.page >= data.total_pages}
              onClick={() => change({ page: state.page + 1 })}
            >
              {t("next")}
            </Button>
          </div>
          <p className="collection-note">
            {t("resourcesNote")}
          </p>
        </section>
      )}
      {collectionId && detail && (
        <section className="panel collection-detail" aria-busy={loading}>
          <div className="collection-toolbar">
            <h2>CollectionRun</h2>
            <RunStatus run={detail} />
          </div>
          <code className="collection-id">{detail.id}</code>
          {detail.detailed_observations_available ? (
            <CollectionComparisonActions run={detail} />
          ) : (
            <div className="alert" role="status">
              <strong>{t("expiredDetails")}</strong>
              <p>
                {t("expiredDescription")}
              </p>
            </div>
          )}
          {detail.status === "FAILED" && (
            <div className="alert error" role="alert">
              <strong>{t("failedCollection")}</strong>
              <p>
                {detail.error_detail || t("failureNotRecorded")}
              </p>
            </div>
          )}
          {detail.has_warnings && (
            <div className="alert" role="status">
              <strong>
                {t("completedWithWarnings")}
              </strong>
              <p>
                {detail.warning_detail ||
                  t("analyzersIncomplete")}
              </p>
            </div>
          )}
          {detail.status === "RUNNING" && (
            <p role="status">
              {t("runningDetail", {duration: durationLabel(detail, now)})}
            </p>
          )}
          <dl className="collection-metadata">
            <div>
              <dt>{t("cloud")}</dt>
              <dd>{providerLabel(detail.provider)}</dd>
            </div>
            <div>
              <dt>{t("account")}</dt>
              <dd>
                {detail.account_name || detail.account_id}
                {detail.account_name && <small>{detail.account_id}</small>}
              </dd>
            </div>
            <div>
              <dt>{t("started")}</dt>
              <dd>{preciseDate(detail.started_at)}</dd>
            </div>
            <div>
              <dt>{t("finished")}</dt>
              <dd>{preciseDate(detail.finished_at)}</dd>
            </div>
            <div>
              <dt>{t("duration")}</dt>
              <dd>{durationLabel(detail, now)}</dd>
            </div>
            <div>
              <dt>{t("analyzerVersion")}</dt>
              <dd>{detail.analyzer_version || t("notRecorded")}</dd>
            </div>
            {detail.trigger && (
              <div>
                <dt>{t("trigger")}</dt>
                <dd>
                  {detail.trigger === "manual"
                    ? t("manual")
                    : detail.trigger === "scheduled"
                      ? t("scheduled")
                      : detail.trigger}
                </dd>
              </div>
            )}
            {detail.scan_id && (
              <div>
                <dt>{t("sourceScan")}</dt>
                <dd>
                  <code>{detail.scan_id}</code>
                </dd>
              </div>
            )}
            <div>
              <dt>{t("resourcesAnalyzed")}</dt>
              <dd>
                {detail.resources_analyzed_available
                  ? number(detail.resources_analyzed)
                  : t("unavailable")}
              </dd>
            </div>
            <div>
              <dt>{t("opportunitiesFound")}</dt>
              <dd>
                {detail.status === "RUNNING"
                  ? t("waitingCompletion")
                  : number(detail.opportunities_found)}
              </dd>
            </div>
            <div>
              <dt>{t("retainedObservations")}</dt>
              <dd>{number(detail.opportunities_observed)}</dd>
            </div>
          </dl>
          <p>
            {t("detailSummaryNote")}
          </p>
          {detail.detailed_observations_available ? (
            <>
              <Link className="button primary" href={collectionOpportunitiesUrl(detail.id)}>
                {t("viewOpportunities")}
              </Link>
              <p className="collection-note">
                {t("opportunityNavigationNote")}
              </p>
            </>
          ) : (
            <p className="collection-note">
              {t("expiredOpportunitiesNote")}
            </p>
          )}
        </section>
      )}
    </>
  );
}
