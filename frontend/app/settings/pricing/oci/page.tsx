"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
      setError(apiMessage(err, "Falha ao carregar o catálogo OCI."));
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
      "Desativar este preço?\n\nEle deixará de ser considerado em novos cálculos OCI quando não existir outra vigência válida para o mesmo SKU.",
    );
    if (!confirmed) return;
    const reason = window.prompt(
      "Motivo da alteração (mínimo 3 caracteres):",
      "",
    )?.trim();
    if (!reason || reason.length < 3) {
      setError("Informe o motivo da alteração com pelo menos 3 caracteres.");
      return;
    }
    setError("");
    setMessage("");
    try {
      await api(`/pricing/oci/${item.id}/deactivate`, {
        method: "POST",
        body: JSON.stringify({ reason }),
      });
      setMessage(`Preço ${item.sku} desativado.`);
      await load();
    } catch (err) {
      setError(apiMessage(err, "Não foi possível desativar o preço."));
    }
  }

  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES · PRICING · OCI"
        title="Pricing OCI"
        description="Administre preços unitários OCI persistidos pelo DeepOps. Os valores atuais desta área são denominados em BRL."
        actions={
          <button className="button primary" onClick={() => setForm({ mode: "create" })}>
            <Plus size={16} /> Novo preço
          </button>
        }
      />

      {error && <div className="alert error" role="alert">{error}</div>}
      {message && <div className="alert success"><Check size={17} />{message}</div>}

      <section className={`panel ${styles.filters}`}>
        <form onSubmit={applySearch} className={styles.search}>
          <label>
            <span>Pesquisar</span>
            <div className={styles.searchInput}>
              <Search size={16} />
              <input
                value={queryDraft}
                onChange={(event) => setQueryDraft(event.target.value)}
                placeholder="SKU, descrição, item ou shape"
              />
            </div>
          </label>
          <button className="button ghost" type="submit">Buscar</button>
        </form>
        <label>
          <span>Serviço</span>
          <select
            value={service}
            onChange={(event) => {
              setOffset(0);
              setService(event.target.value);
            }}
          >
            <option value="">Todos</option>
            {meta?.services.map((value) => <option key={value} value={value}>{serviceLabel(value)}</option>)}
          </select>
        </label>
        <label>
          <span>Status</span>
          <select
            value={status}
            onChange={(event) => {
              setOffset(0);
              setStatus(event.target.value);
            }}
          >
            <option value="active">Ativos</option>
            <option value="inactive">Inativos</option>
            <option value="future">Futuros</option>
            <option value="expired">Expirados</option>
            <option value="all">Todos</option>
          </select>
        </label>
      </section>

      <section className={`panel ${styles.catalog}`}>
        {loading ? (
          <div className={styles.state} role="status">Carregando preços…</div>
        ) : items.length === 0 ? (
          <div className={styles.state}>
            {query || service || status !== "active"
              ? "Nenhum preço corresponde aos filtros selecionados."
              : "Nenhum preço encontrado."}
          </div>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Serviço</th>
                  <th>SKU</th>
                  <th>Descrição</th>
                  <th>Unidade</th>
                  <th>Preço</th>
                  <th>Vigência</th>
                  <th>Status</th>
                  <th>Origem</th>
                  <th aria-label="Ações" />
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
                      <td>{unitLabel(item.unit)}</td>
                      <td>
                        <strong>{formatBrlDecimal(item.price)}</strong>
                        <small>{item.currency}</small>
                      </td>
                      <td>{formatRange(item)}</td>
                      <td><span className={statusClass(itemStatus)}>{pricingStatusLabel(itemStatus)}</span></td>
                      <td>{sourceLabel(item.source)}</td>
                      <td>
                        <div className={styles.rowActions}>
                          <button className="button small ghost" onClick={() => setHistoryItem(item)}>
                            <History size={14} /> Vigências
                          </button>
                          <button className="button small ghost" onClick={() => setAuditItem(item)}>
                            Auditoria
                          </button>
                          {item.enabled && itemStatus !== "expired" && (
                            <>
                              <button className="button small ghost" onClick={() => setForm({ mode: "edit", item })}>
                                <Pencil size={14} /> Alterar
                              </button>
                              <button className="button small ghost" onClick={() => void deactivate(item)}>
                                <XCircle size={14} /> Desativar
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
          <span>{total} registro{total === 1 ? "" : "s"} · página {pageNumber} de {pageCount}</span>
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
      setError("Informe um preço decimal válido com até 8 casas decimais.");
      return;
    }
    if (!startsAt) {
      setError("Informe uma vigência válida.");
      return;
    }
    if (mode === "edit" && normalizedReason.length < 3) {
      setError("Informe o motivo da alteração com pelo menos 3 caracteres.");
      return;
    }
    if (mode === "create" && normalizedReason && normalizedReason.length < 3) {
      setError("Quando informado, o motivo deve ter pelo menos 3 caracteres.");
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
        await onSaved(`Preço ${sku} cadastrado.`);
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
        await onSaved(`Nova vigência de ${item.sku} criada.`);
      }
    } catch (err) {
      setError(apiMessage(err, "Não foi possível salvar o preço."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className={styles.overlay} role="presentation">
      <section className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="pricing-form-title">
        <div className={styles.modalHeader}>
          <div>
            <div className="eyebrow">PRICING OCI</div>
            <h2 id="pricing-form-title">{mode === "create" ? "Novo preço" : "Alterar preço"}</h2>
          </div>
          <button className="button small ghost" onClick={onClose} disabled={saving}>Fechar</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        <form onSubmit={submit} className={styles.form}>
          <div className={styles.formGrid}>
            <ReadOnlyField label="Provider" value="OCI" />
            <ReadOnlyField label="Moeda" value="BRL" />
            <label>
              <span>Serviço</span>
              <input
                list="pricing-services"
                value={service}
                onChange={(event) => setService(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>SKU</span>
              <input
                value={sku}
                onChange={(event) => setSku(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>Unidade</span>
              <input
                list="pricing-units"
                value={unit}
                onChange={(event) => setUnit(event.target.value)}
                disabled={mode === "edit" || saving}
                required
              />
            </label>
            <label>
              <span>Preço unitário</span>
              <input
                inputMode="decimal"
                value={price}
                onChange={(event) => setPrice(event.target.value)}
                placeholder="0,00000000"
                disabled={saving}
                required
              />
              <small>Decimal com até 8 casas. Persistido sem formatação monetária.</small>
            </label>
            <label className={styles.fullField}>
              <span>Descrição</span>
              <input
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                disabled={saving}
                required
              />
            </label>
            <label>
              <span>Vigente a partir de</span>
              <input
                type="datetime-local"
                value={effectiveFrom}
                onChange={(event) => setEffectiveFrom(event.target.value)}
                disabled={saving}
                required
              />
            </label>
            <label className={styles.fullField}>
              <span>Motivo da alteração{mode === "create" ? " (opcional)" : ""}</span>
              <input
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Ex.: Atualização da tabela OCI de outubro/2026"
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
                Cadastrar como ativo
              </label>
            )}
          </div>
          {mode === "edit" && item && (
            <div className={styles.preview}>
              <strong>Alteração não destrutiva</strong>
              <span>Preço atual: {formatBrlDecimal(item.price)}</span>
              <span>Novo preço: {normalizedPrice ? formatBrlDecimal(normalizedPrice) : "—"}</span>
              <span>A versão atual será encerrada na nova vigência; o valor anterior continuará no histórico.</span>
            </div>
          )}
          <div className={styles.formActions}>
            <button type="button" className="button ghost" onClick={onClose} disabled={saving}>Cancelar</button>
            <button type="submit" className="button primary" disabled={saving}>
              {saving ? "Salvando…" : mode === "create" ? "Cadastrar preço" : "Criar nova vigência"}
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
        if (active) setError(apiMessage(err, "Não foi possível carregar as vigências."));
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
            <div className="eyebrow">HISTÓRICO DE VIGÊNCIAS</div>
            <h2 id="pricing-history-title">{item.sku}</h2>
          </div>
          <button className="button small ghost" onClick={onClose}>Fechar</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {loading ? <div className={styles.state}>Carregando vigências…</div> : (
          <div className={styles.historyList}>
            {rows.map((row) => (
              <article key={row.id}>
                <div>
                  <strong>{formatBrlDecimal(row.price)}</strong>
                  <span>{row.currency} · {unitLabel(row.unit)}</span>
                </div>
                <div>
                  <strong>{formatRange(row)}</strong>
                  <span>{pricingStatusLabel(pricingLifecycleStatus(row))}</span>
                </div>
                <div>
                  <strong>{sourceLabel(row.source)}</strong>
                  <span>{row.enabled ? "Habilitado" : "Desabilitado"}</span>
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
        if (active) setError(apiMessage(err, "Não foi possível carregar a auditoria."));
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
            <div className="eyebrow">AUDITORIA</div>
            <h2 id="pricing-audit-title">{item.sku}</h2>
          </div>
          <button className="button small ghost" onClick={onClose}>Fechar</button>
        </div>
        {error && <div className="alert error" role="alert">{error}</div>}
        {loading ? (
          <div className={styles.state} role="status">Carregando auditoria…</div>
        ) : !data || data.items.length === 0 ? (
          <div className={styles.state}>Nenhum evento de auditoria registrado para este pricing key.</div>
        ) : (
          <>
            <div className={styles.historyList}>
              {data.items.map((event) => (
                <article key={event.id}>
                  <div>
                    <strong>{auditActionLabel(event.action)}</strong>
                    <span>{formatAuditDate(event.occurred_at)}</span>
                  </div>
                  <div>
                    <strong>{auditActorLabel(event)}</strong>
                    <span>{event.reason ? `Motivo: ${event.reason}` : "Sem motivo informado"}</span>
                  </div>
                  <div>
                    <strong>{auditDiff(event)}</strong>
                    <span>Versão: {event.pricing_item_id}</span>
                  </div>
                </article>
              ))}
            </div>
            <div className={styles.pagination}>
              <span>{data.total} evento{data.total === 1 ? "" : "s"} · página {data.page} de {Math.max(1, data.total_pages)}</span>
              <div>
                <button className="button small ghost" disabled={page <= 1 || loading} onClick={() => setPage(page - 1)}>Anterior</button>
                <button className="button small ghost" disabled={page >= data.total_pages || loading} onClick={() => setPage(page + 1)}>Próxima</button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

function auditActionLabel(action: string) {
  const labels: Record<string, string> = {
    CREATED: "Preço criado",
    PRICE_CHANGED: "Preço alterado",
    FUTURE_VERSION_CREATED: "Vigência futura criada",
    METADATA_CHANGED: "Metadados alterados",
    DEACTIVATED: "Preço desativado",
    REACTIVATED: "Preço reativado",
    VALIDITY_CHANGED: "Vigência alterada",
    IMPORTED: "Preço importado",
  };
  return labels[action] ?? action;
}

function auditActorLabel(event: PricingAuditEvent) {
  if (event.actor_type === "SYSTEM") return "Sistema";
  return event.actor_name || event.actor_email || "Usuário removido";
}

function auditDiff(event: PricingAuditEvent) {
  const before = event.before_data;
  const after = event.after_data;
  if (!before && after?.price) {
    return `Preço: ${formatBrlDecimal(after.price)} ${after.currency ?? ""}`.trim();
  }
  if (before?.price !== after?.price && before?.price && after?.price) {
    return `Preço: ${formatBrlDecimal(before.price)} → ${formatBrlDecimal(after.price)} ${after.currency ?? before.currency ?? ""}`.trim();
  }
  if (before?.enabled !== after?.enabled && before?.enabled !== undefined && after?.enabled !== undefined) {
    return `Status: ${before.enabled ? "habilitado" : "desabilitado"} → ${after.enabled ? "habilitado" : "desabilitado"}`;
  }
  if (before?.effective_until !== after?.effective_until) {
    return `Fim da vigência: ${formatAuditOptionalDate(before?.effective_until)} → ${formatAuditOptionalDate(after?.effective_until)}`;
  }
  if (before?.description !== after?.description) {
    return "Descrição alterada";
  }
  return "Alteração registrada";
}

function formatAuditOptionalDate(value: string | null | undefined) {
  return value ? formatAuditDate(value) : "aberta";
}

function formatAuditDate(value: string) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  return <label><span>{label}</span><input value={value} readOnly disabled /></label>;
}

function formatRange(item: PricingItem) {
  const formatter = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });
  const start = formatter.format(new Date(item.effective_from));
  const end = item.effective_until ? formatter.format(new Date(item.effective_until)) : "aberta";
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
