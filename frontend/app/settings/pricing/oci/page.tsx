"use client";

import { NativeSelect } from "@/components/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import {formatLocaleDateTime} from "@/i18n/formatters.mjs";
import { Check, History, Pencil, Plus, Search, XCircle } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import {
  datetimeLocalToIso,
  formatBrlDecimal,
  normalizeDecimalInput,
  pricingLifecycleStatus,
  pricingStatusLabel,
  sourceLabel,
  toDatetimeLocal,
  unitLabel,
} from "@/lib/pricing.mjs";
import styles from "./pricing.module.css";

type PricingItem = {
  id: string;
  provider: string;
  service: string;
  sku: string;
  description: string;
  unit: string;
  price: string;
  currency: string;
  effective_from: string;
  effective_until: string | null;
  enabled: boolean;
  source: string;
  created_at: string;
  updated_at: string;
};

type PricingList = {
  items: PricingItem[];
  total: number;
  limit: number;
  offset: number;
};

type PricingMeta = {
  provider: string;
  currency: string;
  services: string[];
  units: string[];
  sources: string[];
};

type AuditSnapshot = {
  id?: string;
  price?: string;
  currency?: string;
  description?: string;
  effective_from?: string;
  effective_until?: string | null;
  enabled?: boolean;
  source?: string;
};

type PricingAuditEvent = {
  id: string;
  pricing_item_id: string;
  action: string;
  actor_type: string;
  actor_name: string | null;
  actor_email: string | null;
  reason: string | null;
  before_data: AuditSnapshot | null;
  after_data: AuditSnapshot | null;
  occurred_at: string;
};

type PricingAuditPage = {
  items: PricingAuditEvent[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

const PAGE_SIZE = 25;
const AUDIT_PAGE_SIZE = 10;

function apiMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

export default function OciPricingPage() {
  const locale = useLocale();
  const t = useTranslations("settings.ociPricing");
  const statusWords: Record<string, string> = {active:t("statusActive"),inactive:t("statusInactive"),future:t("statusFuture"),expired:t("statusExpired")};
  const sourceWords: Record<string, string> = {IMPORTED_OCI_CALCULATOR:t("sourceImported"),MANUAL:t("sourceManual")};
  const unitWords: Record<string, string> = {OCPU_HOUR:t("unitOcpu"),GB_RAM_HOUR:t("unitRam"),GB_MONTH:t("unitGb"),VPU_GB_MONTH:t("unitVpu"),INSTANCE_HOUR:t("unitInstance")};
  const [items, setItems] = useState<PricingItem[]>([]);
  const [meta, setMeta] = useState<PricingMeta | null>(null);
  const [total, setTotal] = useState(0);
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [service, setService] = useState("");
  const [status, setStatus] = useState("active");
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState<{ mode: "create" | "edit"; item?: PricingItem } | null>(null);
  const [historyItem, setHistoryItem] = useState<PricingItem | null>(null);
  const [auditItem, setAuditItem] = useState<PricingItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({
        status,
        limit: String(PAGE_SIZE),
        offset: String(offset),
      });
      if (query) params.set("q", query);
      if (service) params.set("service", service);
      const [data, metadata] = await Promise.all([
        api<PricingList>(`/pricing/oci?${params}`),
        meta ? Promise.resolve(meta) : api<PricingMeta>("/pricing/oci/meta"),
      ]);
      setItems(data.items);
      setTotal(data.total);
      setMeta(metadata);
    } catch (err) {
      setError(apiMessage(err, t("loadFailed")));
    } finally {
      setLoading(false);
    }
  }, [meta, offset, query, service, status]);

  useEffect(() => {
    void load();
  }, [load]);

  function applySearch(event: React.FormEvent) {
    event.preventDefault();
    setOffset(0);
    setQuery(queryDraft.trim());
  }

  async function deactivate(item: PricingItem) {
    const confirmed = window.confirm(
      t("deactivateConfirm"),
    );
    if (!confirmed) return;
    const reason = window.prompt(
      t("reasonPrompt"),
      "",
    )?.trim();
    if (!reason || reason.length < 3) {
      setError(t("reasonTooShort"));
      return;
    }
    setError("");
    setMessage("");
    try {
      await api(`/pricing/oci/${item.id}/deactivate`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setMessage(t("priceDeactivated", {sku: item.sku}));
      await load();
    } catch (err) {
      setError(apiMessage(err, t("deactivateFailed")));
    }
  }

  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <button className="button primary" onClick={() => setForm({ mode: "create" })}>
            <Plus size={16} /> {t("newPrice")}
          </button>
        }
      />

      {error && <div className="alert error" role="alert">{error}</div>}
      {message && <div className="alert success"><Check size={17} />{message}</div>}

      <section className={`panel ${styles.filters}`}>
        <form onSubmit={applySearch} className={styles.search}>
          <label>
            <span>{t("search")}</span>
            <div className={styles.searchInput}>
              <Search size={16} />
              <input
                value={queryDraft}
                onChange={(event) => setQueryDraft(event.target.value)}
                placeholder={t("searchPlaceholder")}
              />
            </div>
          </label>
          <button className="button ghost" type="submit">{t("searchButton")}</button>
        </form>
        <label>
          <span>{t("service")}</span>
          <NativeSelect
            value={service}
            onChange={(event) => {
              setOffset(0);
              setService(event.target.value);
            }}
          >
            <option value="">{t("all")}</option>
            {meta?.services.map((value) => <option key={value} value={value}>{serviceLabel(value)}</option>)}
          </NativeSelect>
        </label>
        <label>
          <span>{t("status")}</span>
          <NativeSelect
            value={status}
            onChange={(event) => {
              setOffset(0);
              setStatus(event.target.value);
            }}
          >
            <option value="active">{t("activePlural")}</option>
            <option value="inactive">{t("inactivePlural")}</option>
            <option value="future">{t("futurePlural")}</option>
            <option value="expired">{t("expiredPlural")}</option>
            <option value="all">{t("all")}</option>
          </NativeSelect>
        </label>
      </section>

      <section className={`panel ${styles.catalog}`}>
        {loading ? (
          <div className={styles.state} role="status">{t("loading")}</div>
        ) : items.length === 0 ? (
          <div className={styles.state}>
            {query || service || status !== "active"
              ? t("noFiltered")
              : t("noResults")}
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t("service")}</th>
                  <th>{t("sku")}</th>
                  <th>{t("itemDescription")}</th>
                  <th>{t("unit")}</th>
                  <th>{t("price")}</th>
                  <th>{t("validity")}</th>
                  <th>{t("status")}</th>
                  <th>{t("source")}</th>
                  <th aria-label={t("actions")} />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const itemStatus = pricingLifecycleStatus(item);
                  return (
                    <tr key={item.id}>
                      <td>{serviceLabel(item.service)}</td>
                      <td><code>{item.sku}</code></td>
                      <td>{item.description}</td>
                      <td>{unitWords[item.unit] ?? unitLabel(item.unit)}</td>
                      <td>
                        <strong>{formatBrlDecimal(item.price, locale)}</strong>
                        <small>{item.currency}</small>
                      </td>
                      <td>{formatRange(item, locale)}</td>
                      <td><span className={statusClass(itemStatus)}>{statusWords[itemStatus] ?? pricingStatusLabel(itemStatus)}</span></td>
                      <td>{sourceWords[item.source] ?? sourceLabel(item.source)}</td>
                      <td>
                        <div className={styles.rowActions}>
                          <button className="button small ghost" onClick={() => setHistoryItem(item)}>
                            <History size={14} /> {t("versions")}
                          </button>
                          <button className="button small ghost" onClick={() => setAuditItem(item)}>
                            Auditoria
                          </button>
                          {item.enabled && itemStatus !== "expired" && (
                            <>
                              <button className="button small ghost" onClick={() => setForm({ mode: "edit", item })}>
                                <Pencil size={14} /> {t("edit")}
                              </button>
                              <button className="button small ghost" onClick={() => void deactivate(item)}>
                                <XCircle size={14} /> {t("deactivate")}
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className={styles.pagination}>
          <span>{t("recordCount", {count: total, page: pageNumber, pages: pageCount})}</span>
          <div>
            <button
              className="button small ghost"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Anterior
            </button>
            <button
              className="button small ghost"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Próxima
            </button>
          </div>
        </div>
      </section>

      {form && (
        <PricingForm
          mode={form.mode}
          item={form.item}
          meta={meta}
          onClose={() => setForm(null)}
          onSaved={async (text) => {
            setForm(null);
            setMessage(text);
            setError("");
            await load();
          }}
        />
      )}
      {historyItem && <PricingHistory item={historyItem} onClose={() => setHistoryItem(null)} />}
      {auditItem && <PricingAuditHistory item={auditItem} onClose={() => setAuditItem(null)} />}
    </>
  );
}

function PricingForm({
  mode,
  item,
  meta,
  onClose,
  onSaved,
}: {
  mode: "create" | "edit";
  item?: PricingItem;
  meta: PricingMeta | null;
  onClose: () => void;
  onSaved: (message: string) => Promise<void>;
}) {
  const locale = useLocale();
  const t = useTranslations("settings.ociPricing");
  const [service, setService] = useState(item?.service ?? meta?.services[0] ?? "");
  const [sku, setSku] = useState(item?.sku ?? "");
  const [description, setDescription] = useState(item?.description ?? "");
  const [unit, setUnit] = useState(item?.unit ?? meta?.units[0] ?? "");
  const [price, setPrice] = useState(item?.price ?? "");
  const [effectiveFrom, setEffectiveFrom] = useState(toDatetimeLocal(new Date()));
  const [enabled, setEnabled] = useState(true);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const normalizedPrice = useMemo(() => normalizeDecimalInput(price), [price]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const startsAt = datetimeLocalToIso(effectiveFrom);
    const normalizedReason = reason.trim();
    if (!normalizedPrice) {
      setError(t("validPrice"));
      return;
    }
    if (!startsAt) {
      setError(t("validStart"));
      return;
    }
    if (mode === "edit" && normalizedReason.length < 3) {
      setError(t("reasonTooShort"));
      return;
    }
    if (mode === "create" && normalizedReason && normalizedReason.length < 3) {
      setError(t("optionalReason"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      if (mode === "create") {
        await api<PricingItem>("/pricing/oci", {
          method: "POST",
          body: JSON.stringify({
            service,
            sku,
            description,
            unit,
            price: normalizedPrice,
            effective_from: startsAt,
            enabled,
            reason: normalizedReason || undefined,
          }),
        });
        await onSaved(t("priceCreated", {sku}));
      } else if (item) {
        await api<PricingItem>(`/pricing/oci/${item.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            price: normalizedPrice,
            description,
            effective_from: startsAt,
            reason: normalizedReason,
          }),
        });
        await onSaved(t("newVersionCreated", {sku: item.sku}));
      }
    } catch (err) {
      setError(apiMessage(err, t("saveFailed")));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.overlay} role="presentation">
      <section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="pricing-form-title">
        <div className={styles.modalHeader}>
          <div>
            <div className="eyebrow">{t("formEyebrow")}</div>
            <h2 id="pricing-form-title">{mode === "create" ? t("newPrice") : t("editPrice")}</h2>
          </div>
          <button className="button small ghost" onClick={onClose} disabled={saving}>{t("close")}</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        <form onSubmit={submit} className={styles.form}>
          <div className={styles.formGrid}>
            <ReadOnlyField label={t("provider")} value="OCI" />
            <ReadOnlyField label={t("currency")} value="BRL" />
            <label>
              <span>{t("service")}</span>
              <input
                list="pricing-services"
                value={service}
                onChange={(event) => setService(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>{t("sku")}</span>
              <input
                value={sku}
                onChange={(event) => setSku(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>{t("unit")}</span>
              <input
                list="pricing-units"
                value={unit}
                onChange={(event) => setUnit(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>{t("unitPrice")}</span>
              <input
                inputMode="decimal"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                placeholder={locale === "en-US" ? "0.00000000" : "0,00000000"}
                disabled={saving}
                required
              />
              <small>{t("decimalHelp")}</small>
            </label>
            <label className={styles.fullField}>
              <span>{t("itemDescription")}</span>
              <input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                disabled={saving}
                required
              />
            </label>
            <label>
              <span>{t("validFrom")}</span>
              <input
                type="datetime-local"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
                disabled={saving}
                required
              />
            </label>
            <label className={styles.fullField}>
              <span>{t("reason")}{mode === "create" ? " (" + t("optional") + ")" : ""}</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder={t("reasonPlaceholder")}
                disabled={saving}
                required={mode === "edit"}
                minLength={mode === "edit" ? 3 : undefined}
                maxLength={500}
              />
            </label>
            {mode === "create" && (
              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(event) => setEnabled(event.target.checked)}
                  disabled={saving}
                />
                {t("createEnabled")}
              </label>
            )}
          </div>
          {mode === "edit" && item && (
            <div className={styles.preview}>
              <strong>{t("nonDestructive")}</strong>
              <span>{t("currentPrice")}: {formatBrlDecimal(item.price, locale)}</span>
              <span>{t("nextPrice")}: {normalizedPrice ? formatBrlDecimal(normalizedPrice, locale) : "—"}</span>
              <span>{t("previewHelp")}</span>
            </div>
          )}
          <div className={styles.formActions}>
            <button type="button" className="button ghost" onClick={onClose} disabled={saving}>{t("cancel")}</button>
            <button type="submit" className="button primary" disabled={saving}>
              {saving ? t("saving") : mode === "create" ? t("createPrice") : t("createVersion")}
            </button>
          </div>
          <datalist id="pricing-services">{meta?.services.map((value) => <option key={value} value={value} />)}</datalist>
          <datalist id="pricing-units">{meta?.units.map((value) => <option key={value} value={value} />)}</datalist>
        </form>
      </section>
    </div>
  );
}

function PricingHistory({ item, onClose }: { item: PricingItem; onClose: () => void }) {
  const locale = useLocale();
  const t = useTranslations("settings.ociPricing");
  const statusWords: Record<string, string> = {active:t("statusActive"),inactive:t("statusInactive"),future:t("statusFuture"),expired:t("statusExpired")};
  const sourceWords: Record<string, string> = {IMPORTED_OCI_CALCULATOR:t("sourceImported"),MANUAL:t("sourceManual")};
  const unitWords: Record<string, string> = {OCPU_HOUR:t("unitOcpu"),GB_RAM_HOUR:t("unitRam"),GB_MONTH:t("unitGb"),VPU_GB_MONTH:t("unitVpu"),INSTANCE_HOUR:t("unitInstance")};
  const [rows, setRows] = useState<PricingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    api<PricingItem[]>(`/pricing/oci/${item.id}/history`)
      .then((data) => {
        if (active) setRows(data);
      })
      .catch((err) => {
        if (active) setError(apiMessage(err, t("historyFailed")));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [item.id]);

  return (
    <div className={styles.overlay} role="presentation">
      <section className={`${styles.modal} ${styles.historyModal}`} role="dialog" aria-modal="true" aria-labelledby="pricing-history-title">
        <div className={styles.modalHeader}>
          <div>
            <div className="eyebrow">{t("historyEyebrow")}</div>
            <h2 id="pricing-history-title">{item.sku}</h2>
          </div>
          <button className="button small ghost" onClick={onClose}>{t("close")}</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {loading ? <div className={styles.state}>{t("historyLoading")}</div> : (
          <div className={styles.historyList}>
            {rows.map((row) => (
              <article key={row.id}>
                <div>
                  <strong>{formatBrlDecimal(row.price, locale)}</strong>
                  <span>{row.currency} · {unitWords[row.unit] ?? unitLabel(row.unit)}</span>
                </div>
                <div>
                  <strong>{formatRange(row, locale)}</strong>
                  <span>{statusWords[pricingLifecycleStatus(row)] ?? pricingStatusLabel(pricingLifecycleStatus(row))}</span>
                </div>
                <div>
                  <strong>{sourceWords[row.source] ?? sourceLabel(row.source)}</strong>
                  <span>{row.enabled ? t("statusEnabled") : t("statusDisabled")}</span>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function PricingAuditHistory({ item, onClose }: { item: PricingItem; onClose: () => void }) {
  const locale = useLocale();
  const t = useTranslations("settings.ociPricing");
  const actionWords: Record<string, string> = {CREATED:t("actionCreated"),PRICE_CHANGED:t("actionChanged"),FUTURE_VERSION_CREATED:t("actionFuture"),METADATA_CHANGED:t("actionMetadata"),DEACTIVATED:t("actionDeactivated"),REACTIVATED:t("actionReactivated"),VALIDITY_CHANGED:t("actionValidity"),IMPORTED:t("actionImported")};
  const auditWords = {price:t("price"),status:t("status"),enabled:t("statusEnabled"),disabled:t("statusDisabled"),endValidity:t("endValidity"),descriptionChanged:t("descriptionChanged"),changeRecorded:t("changeRecorded"),open:t("openEnded")};
  const [data, setData] = useState<PricingAuditPage | null>(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api<PricingAuditPage>(`/pricing/oci/${item.id}/audit?page=${page}&page_size=${AUDIT_PAGE_SIZE}`)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        if (active) setError(apiMessage(err, t("auditFailed")));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [item.id, page]);

  return (
    <div className={styles.overlay} role="presentation">
      <section className={`${styles.modal} ${styles.historyModal}`} role="dialog" aria-modal="true" aria-labelledby="pricing-audit-title">
        <div className={styles.modalHeader}>
          <div>
            <div className="eyebrow">{t("auditEyebrow")}</div>
            <h2 id="pricing-audit-title">{item.sku}</h2>
          </div>
          <button className="button small ghost" onClick={onClose}>{t("close")}</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {loading ? (
          <div className={styles.state} role="status">{t("auditLoading")}</div>
        ) : !data || data.items.length === 0 ? (
          <div className={styles.state}>{t("auditEmpty")}</div>
        ) : (
          <>
            <div className={styles.historyList}>
              {data.items.map((event) => (
                <article key={event.id}>
                  <div>
                    <strong>{auditActionLabel(event.action, actionWords)}</strong>
                    <span>{formatAuditDate(event.occurred_at, locale)}</span>
                  </div>
                  <div>
                    <strong>{auditActorLabel(event, t("actorSystem"), t("actorRemoved"))}</strong>
                    <span>{event.reason ? t("auditReason") + ": " + event.reason : t("noReason")}</span>
                  </div>
                  <div>
                    <strong>{auditDiff(event, locale, auditWords)}</strong>
                    <span>{t("version")}: {event.pricing_item_id}</span>
                  </div>
                </article>
              ))}
            </div>
            <div className={styles.pagination}>
              <span>{t("eventCount", {count: data.total, page: data.page, pages: Math.max(1, data.total_pages)})}</span>
              <div>
                <button className="button small ghost" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>{t("previous")}</button>
                <button className="button small ghost" disabled={page >= data.total_pages || loading} onClick={() => setPage(page + 1)}>{t("next")}</button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function auditActionLabel(action: string, labels: Record<string, string>) {
  return labels[action] ?? action;
}

function auditActorLabel(event: PricingAuditEvent, system: string, removed: string) {
  if (event.actor_type === "SYSTEM") return system;
  return event.actor_name || event.actor_email || removed;
}

type AuditWords = {price: string; status: string; enabled: string; disabled: string; endValidity: string; descriptionChanged: string; changeRecorded: string; open: string};
function auditDiff(event: PricingAuditEvent, locale: string, words: AuditWords) {
  const before = event.before_data;
  const after = event.after_data;
  if (!before && after?.price) return `${words.price}: ${formatBrlDecimal(after.price, locale)} ${after.currency ?? ""}`.trim();
  if (before?.price !== after?.price && before?.price && after?.price) return `${words.price}: ${formatBrlDecimal(before.price, locale)} → ${formatBrlDecimal(after.price, locale)} ${after.currency ?? before.currency ?? ""}`.trim();
  if (before?.enabled !== after?.enabled && before?.enabled !== undefined && after?.enabled !== undefined) return `${words.status}: ${before.enabled ? words.enabled : words.disabled} → ${after.enabled ? words.enabled : words.disabled}`;
  if (before?.effective_until !== after?.effective_until) return `${words.endValidity}: ${formatAuditOptionalDate(before?.effective_until, locale, words.open)} → ${formatAuditOptionalDate(after?.effective_until, locale, words.open)}`;
  if (before?.description !== after?.description) return words.descriptionChanged;
  return words.changeRecorded;
}

function formatAuditOptionalDate(value: string | null | undefined, locale: string, open: string) {
  return value ? formatAuditDate(value, locale) : open;
}

function formatAuditDate(value: string, locale = "pt-BR") {
  return formatLocaleDateTime(value, locale);
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return <label><span>{label}</span><input value={value} readOnly disabled /></label>;
}

function formatRange(item: PricingItem, locale = "pt-BR") {
  const start = formatLocaleDateTime(item.effective_from, locale);
  const end = item.effective_until ? formatLocaleDateTime(item.effective_until, locale) : (locale === "en-US" ? "open" : "aberta");
  return `${start} → ${end}`;
}

function serviceLabel(value: string) {
  return value === "block_volume" ? "Block Volume" : value === "compute" ? "Compute" : value.replaceAll("_", " ");
}

function statusClass(status: string) {
  return `status-badge ${
    status === "active"
      ? "status-success"
      : status === "future"
        ? "status-running"
        : status === "expired"
          ? "status-untested"
          : "status-error"
  }`;
}
