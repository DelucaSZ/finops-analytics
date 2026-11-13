"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Copy, History, RefreshCw, Search, X } from "lucide-react";
import { NativeSelect } from "@/components/ui";
import { PageHeader } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { formatLocaleDateTime } from "@/i18n/formatters.mjs";
import { formatAwsPrice } from "@/lib/aws-pricing.mjs";
import styles from "./pricing.module.css";

type Meta = {
  provider: string; currency: string; source: string;
  regions: string[]; services: string[]; import_enabled: boolean;
};
type Page<T> = { items: T[]; total: number; limit: number; offset: number };
type Rate = {
  id: string; service: string; service_code: string; region_code: string;
  product_sku: string; product_family: string; description: string;
  product_attributes: Record<string, string>;
  financial_attributes: Record<string, string>;
  rate_code: string; term_code: string; purchase_option: string;
  billing_unit: string; unit: string; rate_description: string;
  begin_range: string; end_range: string;
  pricing_status: string; price: string; currency: string;
  effective_from: string; effective_until: string | null;
  enabled: boolean; source: string; source_effective_at: string | null;
  synced_at: string | null; import_batch_id: string | null;
};
type SyncStatus = {
  service_code: string; region_code: string; last_attempt_status: string;
  catalog_status: string; freshness: string; last_attempt_at: string | null;
  last_verified_at: string | null; last_success_at: string | null;
  next_due_at: string | null; published_batch_id: string | null;
  error_code: string | null;
};
type Coverage = {
  complete: boolean; required: string[]; present: string[];
  missing: string[]; counts: Record<string, number>;
  active_rates: number; products: number;
};
type SyncRun = {
  id: string; service_code: string; region_code: string;
  status: string; trigger: string; attempt: number;
  started_at: string; finished_at: string | null; next_retry_at: string | null;
  products_seen: number; rates_seen: number; rates_published: number;
  rates_rejected: number; source_version: string | null;
  batch_id: string | null; error_code: string | null;
  metrics: Record<string, unknown> | null;
};
type SyncRequest = {
  id: string; status: string; service_code: string; region_code: string;
  requested_at: string; result: Record<string, unknown> | null;
  error_code: string | null;
};

function textError(err: unknown, fallback: string, forbidden: string, busy: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.status === 403) return forbidden;
  if (err.code === "sync_busy") return busy;
  return fallback;
}

function humanDate(value: string | null | undefined, locale: string): string {
  return value ? formatLocaleDateTime(value, locale) : "—";
}

function ShortId({ value }: { value: string | null | undefined }) {
  if (!value) return <>—</>;
  return <code className={styles.shortId} title={value}>{value}</code>;
}

function CopyValue({ value, label }: { value: string; label: string }) {
  return (
    <span className={styles.copyValue}>
      <ShortId value={value} />
      <button
        type="button"
        className="button small ghost"
        aria-label={label}
        title={label}
        onClick={() => void navigator.clipboard?.writeText(value)}
      ><Copy size={14} /></button>
    </span>
  );
}

export default function AwsPricingPage() {
  const t = useTranslations("settings.awsPricing");
  const locale = useLocale();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [region, setRegion] = useState("");
  const [service, setService] = useState("");
  const [status, setStatus] = useState("active");
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [referenceDate, setReferenceDate] = useState("");
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [page, setPage] = useState<Page<Rate>>({ items: [], total: 0, limit: 25, offset: 0 });
  const [loadingMeta, setLoadingMeta] = useState(true);
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [loadingOperations, setLoadingOperations] = useState(false);
  const [error, setError] = useState("");
  const [operationalError, setOperationalError] = useState("");
  const [actionError, setActionError] = useState("");
  const [syncStatuses, setSyncStatuses] = useState<SyncStatus[]>([]);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [runs, setRuns] = useState<Page<SyncRun>>({ items: [], total: 0, limit: 20, offset: 0 });
  const [runOffset, setRunOffset] = useState(0);
  const [selected, setSelected] = useState<Rate | null>(null);
  const [history, setHistory] = useState<Page<Rate> | null>(null);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedRun, setSelectedRun] = useState<SyncRun | null>(null);
  const [request, setRequest] = useState<SyncRequest | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const syncNames: Record<string, string> = useMemo(() => ({
    running: t("states.running"), published: t("states.published"),
    unchanged: t("states.unchanged"), partial: t("states.partial"),
    failed: t("states.failed"), interrupted: t("states.interrupted"),
    never_synced: t("states.neverSynced"), synced: t("states.synced"),
    stale: t("states.stale"), current: t("states.current"),
    not_synced: t("states.neverSynced"), queued: t("states.queued"),
    completed: t("states.completed"), validated: t("states.validated"),
    active: t("states.active"), all: t("states.all"),
    unsupported: t("states.unsupported"), quarantined: t("states.quarantined"),
    withdrawn: t("states.withdrawn"), expired: t("states.expired"),
    future: t("states.future"),
  }), [t]);
  const stateLabel = (value: string) => syncNames[value] ?? value;

  useEffect(() => {
    const controller = new AbortController();
    setLoadingMeta(true);
    api<Meta>("/pricing/aws/meta", { signal: controller.signal })
      .then((data) => {
        if (controller.signal.aborted) return;
        setMeta(data);
        setRegion((old) => data.regions.includes(old) ? old
          : data.regions.includes("sa-east-1") ? "sa-east-1" : data.regions[0] ?? "");
        setService((old) => data.services.includes(old) ? old
          : data.services.includes("AmazonEC2") ? "AmazonEC2" : data.services[0] ?? "");
      })
      .catch(() => { if (!controller.signal.aborted) setError(t("errors.meta")); })
      .finally(() => { if (!controller.signal.aborted) setLoadingMeta(false); });
    return () => controller.abort();
  }, [t]);

  useEffect(() => {
    const timeout = window.setTimeout(() => {
      setOffset(0);
      setQuery(draft.trim());
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [draft]);

  useEffect(() => {
    if (!region) return;
    const controller = new AbortController();
    setLoadingCatalog(true);
    setError("");
    const params = new URLSearchParams({
      region, status, limit: String(limit), offset: String(offset),
    });
    if (service) params.set("service", service);
    if (query) params.set("q", query);
    if (referenceDate) params.set("at", referenceDate + "T00:00:00Z");
    api<Page<Rate>>(`/pricing/aws/rates?${params}`, { signal: controller.signal })
      .then((result) => { if (!controller.signal.aborted) setPage(result); })
      .catch((err) => {
        if (!controller.signal.aborted) setError(
          textError(err, t("errors.catalog"), t("errors.forbidden"), t("errors.busy")),
        );
      })
      .finally(() => { if (!controller.signal.aborted) setLoadingCatalog(false); });
    return () => controller.abort();
  }, [region, service, status, query, referenceDate, limit, offset, reload, t]);

  useEffect(() => {
    if (!region) return;
    const controller = new AbortController();
    setOperationalError("");
    setLoadingOperations(true);
    setCoverage(null);
    const params = new URLSearchParams({ region });
    if (service) params.set("service", service);
    const runParams = new URLSearchParams(params);
    runParams.set("limit", "20");
    runParams.set("offset", String(runOffset));
    const statusParams = new URLSearchParams(params);
    statusParams.set("limit", "500");
    const coveragePromise: Promise<Coverage | null> = service
      ? api<Coverage>(`/pricing/aws/sync/coverage?${params}`, { signal: controller.signal })
      : Promise.resolve(null);
    Promise.all([
      api<{ items: SyncStatus[] }>(`/pricing/aws/sync/status?${statusParams}`, { signal: controller.signal }),
      api<Page<SyncRun>>(`/pricing/aws/sync/runs?${runParams}`, { signal: controller.signal }),
      coveragePromise,
    ])
      .then(([states, operationalRuns, report]) => {
        if (controller.signal.aborted) return;
        setSyncStatuses(states.items);
        setRuns(operationalRuns);
        setCoverage(report);
      })
      .catch(() => {
        if (!controller.signal.aborted) setOperationalError(t("errors.operations"));
      })
      .finally(() => { if (!controller.signal.aborted) setLoadingOperations(false); });
    return () => controller.abort();
  }, [region, service, runOffset, reload, t]);

  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    setHistory(null);
    setHistoryLoading(true);
    api<Page<Rate>>(
      `/pricing/aws/rates/${encodeURIComponent(selected.id)}/history?limit=25&offset=${historyOffset}`,
      { signal: controller.signal },
    )
      .then((data) => { if (!controller.signal.aborted) setHistory(data); })
      .catch(() => { if (!controller.signal.aborted) setHistory(null); })
      .finally(() => { if (!controller.signal.aborted) setHistoryLoading(false); });
    return () => controller.abort();
  }, [selected, historyOffset]);

  useEffect(() => {
    if (!request || !["queued", "running"].includes(request.status)) return;
    let active = true;
    const interval = window.setInterval(() => {
      api<SyncRequest>(`/pricing/aws/sync/requests/${encodeURIComponent(request.id)}`)
        .then((data) => {
          if (!active) return;
          setRequest(data);
          if (!["queued", "running"].includes(data.status)) setReload((value) => value + 1);
        })
        .catch(() => { if (active) setActionError(t("errors.poll")); });
    }, 5000);
    return () => { active = false; window.clearInterval(interval); };
  }, [request, t]);

  const selectedStatus = syncStatuses.find(
    (entry) => entry.region_code === region && entry.service_code === service,
  );
  const currentPage = Math.floor(offset / limit) + 1;
  const maxPage = Math.max(1, Math.ceil(page.total / limit));
  const runPage = Math.floor(runOffset / 20) + 1;
  const maxRunPage = Math.max(1, Math.ceil(runs.total / 20));
  const serviceOptions = meta?.services ?? [];
  const regionOptions = meta?.regions ?? [];

  async function submitSync(dryRun = false) {
    if (!region || !service || !meta?.import_enabled) return;
    if (!window.confirm(dryRun ? t("confirmDryRun") : t("confirmSync"))) return;
    setSubmitting(true);
    setActionError("");
    try {
      const result = await api<SyncRequest>("/pricing/aws/sync", {
        method: "POST",
        body: JSON.stringify({ region_code: region, service_code: service, dry_run: dryRun }),
      });
      setRequest(result);
      setReload((value) => value + 1);
    } catch (err) {
      setActionError(textError(err, t("errors.submit"), t("errors.reauth"), t("errors.busy")));
    } finally {
      setSubmitting(false);
    }
  }

  const number = (value: number) => new Intl.NumberFormat(locale).format(value);
  return (
    <div className={styles.page}>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <button type="button" className="button ghost" onClick={() => setReload((v) => v + 1)}>
            <RefreshCw size={16} /> {t("refresh")}
          </button>
        }
      />
      <div className={styles.notice}>
        <strong>{t("officialSource")}:</strong> {meta?.source ?? "AWS_PUBLIC_PRICE_LIST"}
        <span>{t("currency")}: {meta?.currency ?? "USD"}</span>
        {selectedStatus && (
          <span>{t("lastVerified")}: {humanDate(selectedStatus.last_verified_at, locale)}</span>
        )}
      </div>
      {error && <div role="alert" className="alert error">{error}</div>}
      {loadingMeta && !meta ? <div className={styles.state} role="status">{t("loading")}</div>
        : regionOptions.length === 0 ? (
          <div className={styles.state}>{t("emptyRegions")}</div>
        ) : (
          <>
            <section className={`panel ${styles.filters}`} aria-label={t("filters")}>
              <label>{t("region")}
                <NativeSelect id="aws-pricing-region" value={region} onChange={(event) => {
                  setRegion(event.target.value); setOffset(0); setRunOffset(0);
                  setSelected(null); setRequest(null);
                }}>
                  {regionOptions.map((code) => <option key={code} value={code}>{code}</option>)}
                </NativeSelect>
              </label>
              <label>{t("service")}
                <NativeSelect id="aws-pricing-service" value={service} onChange={(event) => {
                  setService(event.target.value); setOffset(0); setRunOffset(0); setSelected(null);
                }}>
                  <option value="">{t("allServices")}</option>
                  {serviceOptions.map((code) => <option key={code} value={code}>{code}</option>)}
                </NativeSelect>
              </label>
              <label>{t("status")}
                <NativeSelect id="aws-pricing-status" value={status} onChange={(event) => {
                  setStatus(event.target.value); setOffset(0);
                }}>
                  {["active", "all", "unsupported", "quarantined", "withdrawn", "expired", "future"]
                    .map((value) => <option key={value} value={value}>{stateLabel(value)}</option>)}
                </NativeSelect>
              </label>
              <label>{t("referenceDate")}
                <input type="date" value={referenceDate} onChange={(event) => {
                  setReferenceDate(event.target.value); setOffset(0);
                }} />
              </label>
              <label className={styles.search}>{t("search")}
                <span className={styles.searchInput}>
                  <Search size={16} aria-hidden="true" />
                  <input value={draft} onChange={(event) => setDraft(event.target.value)}
                    maxLength={160} placeholder={t("searchPlaceholder")} />
                </span>
              </label>
            </section>

            <section className={`panel ${styles.catalog}`} aria-label={t("catalog")}>
              <div className={styles.sectionHeading}>
                <h2>{t("catalog")}</h2>
                <div>{t("resultCount", { count: page.total })}
                  <NativeSelect id="aws-pricing-page-size" value={String(limit)} aria-label={t("pageSize")} onChange={(event) => {
                    setLimit(Number(event.target.value)); setOffset(0);
                  }}>
                    {[25, 50, 100].map((count) =>
                      <option key={count} value={count}>{number(count)}</option>)}
                  </NativeSelect>
                </div>
              </div>
              {loadingCatalog ? <div className={styles.state} role="status">{t("loadingRates")}</div>
                : page.items.length === 0 ? (
                  <div className={styles.state}>{query ? t("emptySearch") : t("emptyRates")}</div>
                ) : (
                  <div className={styles.tableWrap}>
                    <table className={styles.table}>
                      <thead><tr>
                        <th>{t("service")}</th><th>{t("region")}</th>
                        <th>{t("product")}</th><th>{t("sku")}</th>
                        <th>{t("configuration")}</th><th>{t("unit")}</th>
                        <th>{t("price")}</th><th>{t("validity")}</th>
                        <th>{t("status")}</th><th>{t("actions")}</th>
                      </tr></thead>
                      <tbody>{page.items.map((item) => (
                        <tr key={item.id}>
                          <td><ShortId value={item.service_code} /></td>
                          <td>{item.region_code}</td>
                          <td className={styles.description} title={item.description}>{item.description}</td>
                          <td><ShortId value={item.product_sku} /></td>
                          <td className={styles.description} title={item.rate_description}>{item.rate_description}</td>
                          <td><ShortId value={item.unit} /></td>
                          <td><strong title={item.price + " USD"}>{formatAwsPrice(item.price, locale)}</strong></td>
                          <td>{humanDate(item.effective_from, locale)}</td>
                          <td>{stateLabel(item.pricing_status)}</td>
                          <td><button className="button small ghost" onClick={() => {
                            setSelected(item); setHistoryOffset(0);
                          }}>{t("details")}</button></td>
                        </tr>
                      ))}</tbody>
                    </table>
                  </div>
                )}
              <div className={styles.pagination}>
                <span>{t("pages", { page: currentPage, total: maxPage })}</span>
                <div>
                  <button className="button small ghost" disabled={loadingCatalog || offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - limit))}>{t("previous")}</button>
                  <button className="button small ghost"
                    disabled={loadingCatalog || offset + limit >= page.total}
                    onClick={() => setOffset(offset + limit)}>{t("next")}</button>
                </div>
              </div>
            </section>

            <div className={styles.operations}>
              <section className="panel">
                <div className={styles.sectionHeading}><h2>{t("coverage")}</h2></div>
                {loadingOperations ? <p className={styles.muted}>{t("loading")}</p>
                  : !service ? <p className={styles.muted}>{t("selectCoverageService")}</p>
                  : !coverage ? <p className={styles.muted}>{t("coverageUnavailable")}</p> : (
                    <>
                      <div className={styles.metrics}>
                        <div><span>{t("products")}</span><strong>{number(coverage.products)}</strong></div>
                        <div><span>{t("activeRates")}</span><strong>{number(coverage.active_rates)}</strong></div>
                        <div><span>{t("minimumComponents")}</span>
                          <strong>{coverage.present.length}/{coverage.required.length}</strong></div>
                        <div><span>{t("coverageStatus")}</span><strong>
                          {coverage.complete ? t("minimumComplete") : t("minimumPartial")}
                        </strong></div>
                      </div>
                      <p className={styles.muted}>{t("coverageDisclaimer")}</p>
                      {coverage.missing.length > 0 && <div className={styles.missing}>
                        <strong>{t("missingComponents")}</strong>
                        <div>{coverage.missing.map((component) =>
                          <code key={component}>{component}</code>)}</div>
                      </div>}
                    </>
                  )}
              </section>
              <section className="panel">
                <div className={styles.sectionHeading}><h2>{t("sync")}</h2></div>
                {selectedStatus ? (
                  <dl className={styles.summary}>
                    <div><dt>{t("lastAttempt")}</dt><dd>{stateLabel(selectedStatus.last_attempt_status)}</dd></div>
                    <div><dt>{t("catalogState")}</dt><dd>{stateLabel(selectedStatus.catalog_status)}</dd></div>
                    <div><dt>{t("freshness")}</dt><dd>{stateLabel(selectedStatus.freshness)}</dd></div>
                    <div><dt>{t("lastSuccessful")}</dt><dd>{humanDate(selectedStatus.last_success_at, locale)}</dd></div>
                    <div><dt>{t("nextEligible")}</dt><dd>{humanDate(selectedStatus.next_due_at, locale)}</dd></div>
                    <div><dt>{t("publishedBatch")}</dt><dd><ShortId value={selectedStatus.published_batch_id} /></dd></div>
                  </dl>
                ) : <p className={styles.muted}>{t("noSyncState")}</p>}
                <div className={styles.actions}>
                  <button className="button primary" disabled={!service || !meta?.import_enabled || submitting ||
                    (request !== null && ["queued", "running"].includes(request.status))}
                    onClick={() => void submitSync(false)}>{t("syncNow")}</button>
                  <button className="button ghost" disabled={!service || !meta?.import_enabled || submitting ||
                    (request !== null && ["queued", "running"].includes(request.status))}
                    onClick={() => void submitSync(true)}>{t("dryRun")}</button>
                </div>
                {!meta?.import_enabled && <p className={styles.muted}>{t("importDisabled")}</p>}
                {actionError && <div role="alert" className="alert error">{actionError}</div>}
                {request && (
                  <p role="status" className={styles.muted}>
                    {t("requestState")}: {stateLabel(request.status)}
                    {request.error_code ? ` · ${request.error_code}` : ""}
                    {" · "}<ShortId value={request.id} />
                  </p>
                )}
              </section>
            </div>
            {operationalError && <div role="alert" className="alert error">{operationalError}</div>}
            <section className={`panel ${styles.catalog}`}>
              <div className={styles.sectionHeading}><h2>{t("runHistory")}</h2></div>
              {loadingOperations ? <div className={styles.state}>{t("loading")}</div>
                : runs.items.length === 0 ? <div className={styles.state}>{t("emptyRuns")}</div>
                : <div className={styles.tableWrap}>
                  <table className={styles.table}>
                    <thead><tr>
                      <th>{t("date")}</th><th>{t("service")}</th><th>{t("region")}</th>
                      <th>{t("trigger")}</th><th>{t("status")}</th>
                      <th>{t("products")}</th><th>{t("rates")}</th>
                      <th>{t("publishedRates")}</th><th>{t("rejectedRates")}</th>
                      <th>{t("errorCode")}</th><th>{t("actions")}</th>
                    </tr></thead>
                    <tbody>{runs.items.map((run) => <tr key={run.id}>
                      <td>{humanDate(run.started_at, locale)}</td>
                      <td>{run.service_code}</td><td>{run.region_code}</td><td>{run.trigger}</td>
                      <td>{stateLabel(run.status)}</td><td>{number(run.products_seen)}</td>
                      <td>{number(run.rates_seen)}</td><td>{number(run.rates_published)}</td>
                      <td>{number(run.rates_rejected)}</td>
                      <td><ShortId value={run.error_code} /></td>
                      <td><button className="button small ghost" onClick={() => setSelectedRun(run)}>
                        {t("details")}</button></td>
                    </tr>)}</tbody>
                  </table>
                </div>}
              <div className={styles.pagination}>
                <span>{t("pages", { page: runPage, total: maxRunPage })}</span>
                <div>
                  <button className="button small ghost" disabled={runOffset === 0 || loadingOperations}
                    onClick={() => setRunOffset(Math.max(0, runOffset - 20))}>{t("previous")}</button>
                  <button className="button small ghost"
                    disabled={runOffset + 20 >= runs.total || loadingOperations}
                    onClick={() => setRunOffset(runOffset + 20)}>{t("next")}</button>
                </div>
              </div>
            </section>
          </>
        )}

      {selected && <div className={styles.overlay} role="presentation"
        onMouseDown={(event) => { if (event.target === event.currentTarget) setSelected(null); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="aws-pricing-detail"
          className={styles.modal}>
          <div className={styles.modalHeader}>
            <div><h2 id="aws-pricing-detail">{t("rateDetails")}</h2>
              <p>{selected.service_code} · {selected.region_code}</p></div>
            <button className="button small ghost" onClick={() => setSelected(null)}
              aria-label={t("close")}><X size={18} /></button>
          </div>
          <dl className={styles.details}>
            {([
              [t("sku"), selected.product_sku], [t("rateCode"), selected.rate_code],
              [t("productFamily"), selected.product_family],
              [t("configuration"), selected.rate_description],
              [t("unit"), selected.billing_unit], [t("purchaseOption"), selected.purchase_option],
              [t("termCode"), selected.term_code], [t("price"), selected.price + " USD"],
              [t("source"), selected.source], [t("effectiveFrom"), humanDate(selected.effective_from, locale)],
              [t("effectiveUntil"), humanDate(selected.effective_until, locale)],
              [t("importBatch"), selected.import_batch_id ?? "—"],
              [t("status"), stateLabel(selected.pricing_status)],
            ] as [string, string][]).map(([label, value]) =>
              <div key={label}><dt>{label}</dt><dd><CopyValue value={value} label={t("copy")} /></dd></div>)}
          </dl>
          <h3>{t("technicalAttributes")}</h3>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <tbody>{Object.entries(selected.product_attributes ?? {}).map(([key, value]) =>
                <tr key={key}><th>{key}</th><td><CopyValue value={String(value)} label={t("copy")} /></td></tr>)}</tbody>
            </table>
          </div>
          <h3><History size={16} /> {t("rateHistory")}</h3>
          {historyLoading ? <p className={styles.muted}>{t("loading")}</p>
            : history === null ? <p className={styles.muted}>{t("errors.history")}</p>
            : history.items.length === 0 ? <p className={styles.muted}>{t("emptyHistory")}</p>
            : <div className={styles.tableWrap}><table className={styles.table}>
              <thead><tr><th>{t("price")}</th><th>{t("effectiveFrom")}</th>
                <th>{t("effectiveUntil")}</th><th>{t("source")}</th></tr></thead>
              <tbody>{history.items.map((row) => <tr key={row.id}>
                <td>{formatAwsPrice(row.price, locale)}</td>
                <td>{humanDate(row.effective_from, locale)}</td>
                <td>{humanDate(row.effective_until, locale)}</td><td>{row.source}</td>
              </tr>)}</tbody>
            </table></div>}
          {history && <div className={styles.pagination}>
            <span>{t("resultCount", { count: history.total })}</span>
            <div><button className="button small ghost" disabled={historyOffset === 0}
              onClick={() => setHistoryOffset(Math.max(0, historyOffset - 25))}>{t("previous")}</button>
              <button className="button small ghost" disabled={historyOffset + 25 >= history.total}
                onClick={() => setHistoryOffset(historyOffset + 25)}>{t("next")}</button></div>
          </div>}
        </section>
      </div>}

      {selectedRun && <div className={styles.overlay} role="presentation"
        onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedRun(null); }}>
        <section role="dialog" aria-modal="true" aria-labelledby="aws-pricing-run"
          className={styles.modal}>
          <div className={styles.modalHeader}><h2 id="aws-pricing-run">{t("runDetails")}</h2>
            <button className="button small ghost" onClick={() => setSelectedRun(null)}
              aria-label={t("close")}><X size={18} /></button></div>
          <dl className={styles.details}>
            {([
              [t("executionId"), selectedRun.id],
              [t("status"), stateLabel(selectedRun.status)],
              [t("service"), selectedRun.service_code],
              [t("region"), selectedRun.region_code],
              [t("trigger"), selectedRun.trigger],
              [t("date"), humanDate(selectedRun.started_at, locale)],
              [t("finished"), humanDate(selectedRun.finished_at, locale)],
              [t("sourceVersion"), selectedRun.source_version ?? "—"],
              [t("importBatch"), selectedRun.batch_id ?? "—"],
              [t("errorCode"), selectedRun.error_code ?? "—"],
            ] as [string, string][]).map(([label, value]) =>
              <div key={label}><dt>{label}</dt><dd><CopyValue value={value} label={t("copy")} /></dd></div>)}
          </dl>
          {selectedRun.metrics && <pre className={styles.json}>
            {JSON.stringify(selectedRun.metrics, null, 2)}
          </pre>}
        </section>
      </div>}
    </div>
  );
}

