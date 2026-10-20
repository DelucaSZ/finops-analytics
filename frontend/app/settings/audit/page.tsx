"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";

type Actor = {
  id: string | null;
  name: string | null;
  email: string | null;
};

type Entity = {
  type: string;
  id: string | null;
  label: string | null;
};

type Event = {
  id: string;
  event_kind: "security" | "administrative";
  created_at: string;
  actor: Actor;
  module: string;
  action: string;
  entity: Entity;
  source: "UI" | "API" | "SYSTEM" | string;
  reason: string | null;
  changes: Record<string, unknown>;
  metadata: Record<string, unknown>;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  correlation_id: string | null;
};

type Change = { from: unknown; to: unknown };
type UserOption = { id: string; name: string; email: string };
type AuditOption = { value: string; label: string; module?: string | null };
type AuditOptions = { modules: AuditOption[]; actions: AuditOption[] };

type InitialFilters = {
  eventKind: string;
  actorId: string;
  actorSearch: string;
  subjectUserId: string;
  subjectUserSearch: string;
  module: string;
  action: string;
  source: string;
  from: string;
  to: string;
  correlationId: string;
  offset: number;
};

const PAGE_SIZE = 50;

function localDateTime(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function initialFilters(): InitialFilters {
  if (typeof window === "undefined") {
    return {
      eventKind: "all",
      actorId: "",
      actorSearch: "",
      subjectUserId: "",
      subjectUserSearch: "",
      module: "",
      action: "",
      source: "",
      from: "",
      to: "",
      correlationId: "",
      offset: 0,
    };
  }
  const query = new URLSearchParams(window.location.search);
  return {
    eventKind: query.get("event_kind") || "all",
    actorId: query.get("actor_id") || "",
    actorSearch: query.get("actor_search") || "",
    subjectUserId: query.get("subject_user_id") || "",
    subjectUserSearch: query.get("subject_user_search") || "",
    module: query.get("module") || "",
    action: query.get("action") || "",
    source: query.get("source") || "",
    from: localDateTime(query.get("from")),
    to: localDateTime(query.get("to")),
    correlationId: query.get("correlation_id") || "",
    offset: Math.max(0, Number(query.get("offset") || 0) || 0),
  };
}

function fieldLabel(value: string) {
  const known: Record<string, string> = {
    enabled: "Ativa",
    is_active: "Ativo",
    role: "Perfil",
    name: "Nome",
    email: "E-mail",
    scan_interval_hours: "Intervalo da coleta",
    schedule_enabled: "Coleta agendada",
    status: "Status",
    rejection_reason: "Motivo da rejeição",
    archived: "Arquivada",
    is_default: "Padrão",
    granularity: "Granularidade",
    metric: "Métrica",
    group_by: "Agrupamento",
  };
  return known[value] || value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function changeValue(value: unknown, depth = 0): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value);
    return text.length > 120 ? `${text.slice(0, 117)}…` : text;
  }
  if (Array.isArray(value)) {
    const text = value.slice(0, 8).map((item) => changeValue(item, depth + 1)).join(", ");
    return value.length > 8 ? `${text}, … (+${value.length - 8})` : text || "[]";
  }
  if (typeof value === "object" && depth < 2) {
    const entries = Object.entries(value as Record<string, unknown>).slice(0, 6);
    const text = entries.map(([key, item]) => `${fieldLabel(key)}: ${changeValue(item, depth + 1)}`).join(" · ");
    return Object.keys(value as Record<string, unknown>).length > entries.length ? `${text} · …` : text || "{}";
  }
  return "[objeto resumido]";
}

function asChange(value: unknown): Change | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  if (!("from" in value) || !("to" in value)) return null;
  return value as Change;
}

function changeEntries(item: Event): Array<[string, Change]> {
  return Object.entries(item.changes || {}).flatMap(([field, value]) => {
    const change = asChange(value);
    return change ? [[field, change] as [string, Change]] : [];
  });
}

function flattenValues(
  value: Record<string, unknown> | null | undefined,
  prefix = "",
  depth = 0,
): Array<[string, unknown]> {
  if (!value || depth > 2) return [];
  const rows: Array<[string, unknown]> = [];
  for (const [key, item] of Object.entries(value)) {
    if (rows.length >= 30) break;
    const path = prefix ? `${prefix}.${key}` : key;
    if (item && typeof item === "object" && !Array.isArray(item) && depth < 2) {
      rows.push(...flattenValues(item as Record<string, unknown>, path, depth + 1));
    } else {
      rows.push([path, item]);
    }
  }
  return rows.slice(0, 30);
}

function changeSummary(item: Event): string {
  const entries = changeEntries(item);
  if (entries.length) {
    const head = entries
      .slice(0, 2)
      .map(([field, change]) => `${fieldLabel(field)}: ${changeValue(change.from)} → ${changeValue(change.to)}`)
      .join(" · ");
    return entries.length > 2 ? `${head} · +${entries.length - 2}` : head;
  }
  if (item.changes?._truncated) return "Alterações resumidas por limite de tamanho";
  const metadata = flattenValues(item.metadata).slice(0, 2);
  if (metadata.length) {
    return metadata.map(([field, value]) => `${fieldLabel(field)}: ${changeValue(value)}`).join(" · ");
  }
  return item.reason || "Ação registrada sem alteração de campos";
}

function actorLabel(item: Event): { name: string; email: string | null } {
  if (item.event_kind === "administrative" && item.source === "SYSTEM") {
    return { name: "SYSTEM", email: null };
  }
  if (item.actor.name || item.actor.email) {
    return {
      name: item.actor.name || item.actor.email || "Responsável desconhecido",
      email: item.actor.name ? item.actor.email : null,
    };
  }
  if (item.action === "auth.login_failed") return { name: "Tentativa não autenticada", email: null };
  return { name: "Responsável desconhecido", email: null };
}

function fallbackActionLabel(action: string) {
  return action
    .split(".")
    .map((part) => part.replaceAll("_", " "))
    .join(" · ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function toIso(value: string): string {
  return value ? new Date(value).toISOString() : "";
}

function presetRange(hours: number | "today") {
  const now = new Date();
  const start = new Date(now);
  if (hours === "today") start.setHours(0, 0, 0, 0);
  else start.setTime(now.getTime() - hours * 60 * 60 * 1000);
  return { from: localDateTime(start.toISOString()), to: localDateTime(now.toISOString()) };
}

function UserAutocomplete({
  label,
  value,
  selectedId,
  onChange,
  onSelect,
}: {
  label: string;
  value: string;
  selectedId: string;
  onChange: (value: string) => void;
  onSelect: (user: UserOption) => void;
}) {
  const [options, setOptions] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const term = value.trim();
    if (selectedId || term.length < 2) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      api<UserOption[]>(`/audit/users?q=${encodeURIComponent(term)}&limit=20`, { signal: controller.signal })
        .then((rows) => {
          setOptions(rows);
          setOpen(true);
        })
        .catch((error) => {
          if (error?.name !== "AbortError") setOptions([]);
        })
        .finally(() => setLoading(false));
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value, selectedId]);

  return (
    <label style={{ position: "relative" }}>
      {label}
      <input
        value={value}
        maxLength={254}
        placeholder="Nome ou e-mail"
        autoComplete="off"
        onFocus={() => options.length && setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)}
        onChange={(event) => {
          onChange(event.target.value);
          setOpen(true);
        }}
      />
      {loading && <small style={{ color: "var(--muted)" }}>Buscando…</small>}
      {open && options.length > 0 && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            zIndex: 20,
            marginTop: 4,
            padding: 6,
            border: "1px solid var(--border)",
            borderRadius: 9,
            background: "var(--surface-2)",
            boxShadow: "var(--shadow)",
          }}
        >
          {options.map((user) => (
            <button
              key={user.id}
              type="button"
              role="option"
              className="button ghost"
              style={{ width: "100%", justifyContent: "flex-start", marginBottom: 4 }}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => {
                onSelect(user);
                setOpen(false);
              }}
            >
              <span style={{ minWidth: 0, textAlign: "left" }}>
                <strong style={{ display: "block" }}>{user.name}</strong>
                <small style={{ display: "block", overflow: "hidden", textOverflow: "ellipsis" }}>{user.email}</small>
              </span>
            </button>
          ))}
        </div>
      )}
    </label>
  );
}

function DetailRows({ title, values }: { title: string; values: Record<string, unknown> | null }) {
  const rows = flattenValues(values);
  if (!rows.length) return null;
  return (
    <details style={{ marginTop: 12 }}>
      <summary>{title}</summary>
      <div className="data-table-wrap" style={{ marginTop: 8 }}>
        <table className="data-table">
          <tbody>
            {rows.map(([field, value]) => (
              <tr key={field}>
                <th scope="row">{fieldLabel(field)}</th>
                <td>{changeValue(value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

function EventDetail({
  item,
  actionLabel,
  moduleLabel,
  onCorrelation,
}: {
  item: Event;
  actionLabel: string;
  moduleLabel: string;
  onCorrelation: (value: string) => void;
}) {
  const actor = actorLabel(item);
  const entries = changeEntries(item);
  const metadata = flattenValues(item.metadata);
  return (
    <div style={{ padding: "18px 20px", display: "grid", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
        <div><small>Evento</small><strong style={{ display: "block" }}>{actionLabel}</strong></div>
        <div><small>Data</small><strong style={{ display: "block" }}>{formatDate(item.created_at)}</strong></div>
        <div><small>Responsável</small><strong style={{ display: "block" }}>{actor.name}</strong>{actor.email && <span>{actor.email}</span>}</div>
        <div><small>Módulo</small><strong style={{ display: "block" }}>{moduleLabel}</strong></div>
        <div><small>Origem</small><strong style={{ display: "block" }}>{item.source}</strong></div>
        <div><small>Objeto afetado</small><strong style={{ display: "block" }}>{item.entity.label || "—"}</strong><span>{item.entity.type}{item.entity.id ? ` · ${item.entity.id}` : ""}</span></div>
      </div>

      {item.correlation_id && (
        <div>
          <small>Correlation ID</small>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <code>{item.correlation_id}</code>
            <button className="button ghost small" type="button" onClick={() => onCorrelation(item.correlation_id || "")}>Ver eventos relacionados</button>
          </div>
        </div>
      )}

      <div>
        <strong>Alterações</strong>
        {entries.length ? (
          <div className="data-table-wrap" style={{ marginTop: 8 }}>
            <table className="data-table">
              <thead><tr><th>Campo</th><th>Antes</th><th>Depois</th></tr></thead>
              <tbody>
                {entries.map(([field, change]) => (
                  <tr key={field}><td>{fieldLabel(field)}</td><td>{changeValue(change.from)}</td><td>{changeValue(change.to)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: "var(--muted)", margin: "6px 0 0" }}>{item.reason || "Esta ação não possui diff de campos."}</p>
        )}
      </div>

      {metadata.length > 0 && (
        <div>
          <strong>Contexto seguro</strong>
          <div className="data-table-wrap" style={{ marginTop: 8 }}>
            <table className="data-table">
              <tbody>
                {metadata.map(([field, value]) => (
                  <tr key={field}><th scope="row">{fieldLabel(field)}</th><td>{changeValue(value)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <DetailRows title="Snapshot anterior" values={item.before} />
      <DetailRows title="Snapshot posterior" values={item.after} />
    </div>
  );
}

export default function AuditPage() {
  const [initial] = useState(initialFilters);
  const [eventKind, setEventKind] = useState(initial.eventKind);
  const [actorId, setActorId] = useState(initial.actorId);
  const [actorSearch, setActorSearch] = useState(initial.actorSearch);
  const [subjectUserId, setSubjectUserId] = useState(initial.subjectUserId);
  const [subjectUserSearch, setSubjectUserSearch] = useState(initial.subjectUserSearch);
  const [module, setModule] = useState(initial.module);
  const [action, setAction] = useState(initial.action);
  const [source, setSource] = useState(initial.source);
  const [from, setFrom] = useState(initial.from);
  const [to, setTo] = useState(initial.to);
  const [correlationId, setCorrelationId] = useState(initial.correlationId);
  const [offset, setOffset] = useState(initial.offset);
  const [refresh, setRefresh] = useState(0);
  const [expanded, setExpanded] = useState("");
  const [options, setOptions] = useState<AuditOptions>({ modules: [], actions: [] });
  const [data, setData] = useState<{ items: Event[]; total: number }>({ items: [], total: 0 });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api<AuditOptions>("/audit/options").then(setOptions).catch(() => setOptions({ modules: [], actions: [] }));
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const query = new URLSearchParams();
    if (eventKind !== "all") query.set("event_kind", eventKind);
    if (actorId) query.set("actor_id", actorId);
    if (actorSearch.trim()) query.set("actor_search", actorSearch.trim());
    if (subjectUserId) query.set("subject_user_id", subjectUserId);
    if (subjectUserSearch.trim()) query.set("subject_user_search", subjectUserSearch.trim());
    if (module) query.set("module", module);
    if (action) query.set("action", action);
    if (source) query.set("source", source);
    if (from) query.set("from", toIso(from));
    if (to) query.set("to", toIso(to));
    if (correlationId) query.set("correlation_id", correlationId);
    if (offset) query.set("offset", String(offset));
    const suffix = query.toString();
    window.history.replaceState(null, "", `${window.location.pathname}${suffix ? `?${suffix}` : ""}`);
  }, [eventKind, actorId, actorSearch, subjectUserId, subjectUserSearch, module, action, source, from, to, correlationId, offset]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setError("");

    const query = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      event_kind: eventKind,
    });
    if (actorId) query.set("actor_id", actorId);
    else if (actorSearch.trim()) query.set("actor_search", actorSearch.trim());
    if (subjectUserId) query.set("subject_user_id", subjectUserId);
    else if (subjectUserSearch.trim()) query.set("subject_user_search", subjectUserSearch.trim());
    if (module) query.set("module", module);
    if (action) query.set("action", action);
    if (source) query.set("source", source);
    if (from) query.set("from", toIso(from));
    if (to) query.set("to", toIso(to));
    if (correlationId) query.set("correlation_id", correlationId);

    api<{ items: Event[]; total: number }>(`/audit?${query}`, { signal: controller.signal })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        if (active && err?.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [eventKind, actorId, actorSearch, subjectUserId, subjectUserSearch, module, action, source, from, to, correlationId, offset, refresh]);

  const actionOptions = useMemo(
    () => options.actions.filter((item) => !module || item.module === module),
    [options.actions, module],
  );
  const actionLabels = useMemo(() => new Map(options.actions.map((item) => [item.value, item.label])), [options.actions]);
  const moduleLabels = useMemo(() => new Map(options.modules.map((item) => [item.value, item.label])), [options.modules]);

  const activeFilters = useMemo(() => {
    const filters: string[] = [];
    if (actorSearch) filters.push(`Executado por: ${actorSearch}`);
    if (subjectUserSearch) filters.push(`Usuário afetado: ${subjectUserSearch}`);
    if (module) filters.push(`Módulo: ${moduleLabels.get(module) || module}`);
    if (action) filters.push(`Ação: ${actionLabels.get(action) || fallbackActionLabel(action)}`);
    if (source) filters.push(`Origem: ${source}`);
    if (eventKind !== "all") filters.push(`Tipo: ${eventKind === "security" ? "Segurança" : "Administrativo"}`);
    if (from || to) filters.push(`Período: ${from ? new Date(from).toLocaleString("pt-BR") : "início"} → ${to ? new Date(to).toLocaleString("pt-BR") : "agora"}`);
    if (correlationId) filters.push(`Correlation: ${correlationId}`);
    return filters;
  }, [actorSearch, subjectUserSearch, module, action, source, eventKind, from, to, correlationId, moduleLabels, actionLabels]);

  function resetPage() {
    setOffset(0);
    setExpanded("");
  }

  function clearFilters() {
    setEventKind("all");
    setActorId("");
    setActorSearch("");
    setSubjectUserId("");
    setSubjectUserSearch("");
    setModule("");
    setAction("");
    setSource("");
    setFrom("");
    setTo("");
    setCorrelationId("");
    resetPage();
  }

  function applyPreset(hours: number | "today") {
    const range = presetRange(hours);
    setFrom(range.from);
    setTo(range.to);
    resetPage();
  }

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Auditoria"
        description="Trilha cronológica de segurança e alterações administrativas persistentes."
        actions={
          <button className="button" disabled={busy} onClick={() => setRefresh((value) => value + 1)}>
            Atualizar histórico
          </button>
        }
      />

      <p className="settings-help">
        O responsável usa o snapshot histórico do momento do evento. Senhas, tokens, chaves privadas,
        material TLS e outros segredos passam pela sanitização central antes de serem persistidos.
      </p>

      <div className="settings-filters" style={{ alignItems: "end" }}>
        <UserAutocomplete
          label="Executado por"
          value={actorSearch}
          selectedId={actorId}
          onChange={(value) => { setActorSearch(value); setActorId(""); resetPage(); }}
          onSelect={(user) => { setActorId(user.id); setActorSearch(`${user.name} — ${user.email}`); resetPage(); }}
        />
        <UserAutocomplete
          label="Usuário afetado"
          value={subjectUserSearch}
          selectedId={subjectUserId}
          onChange={(value) => { setSubjectUserSearch(value); setSubjectUserId(""); resetPage(); }}
          onSelect={(user) => { setSubjectUserId(user.id); setSubjectUserSearch(`${user.name} — ${user.email}`); resetPage(); }}
        />
        <label>
          Módulo
          <select value={module} onChange={(event) => { setModule(event.target.value); setAction(""); resetPage(); }}>
            <option value="">Todos</option>
            {options.modules.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          Ação
          <select value={action} onChange={(event) => { setAction(event.target.value); resetPage(); }}>
            <option value="">Todas</option>
            {actionOptions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
        <label>
          Origem
          <select value={source} onChange={(event) => { setSource(event.target.value); resetPage(); }}>
            <option value="">Todas</option>
            <option value="UI">UI</option>
            <option value="API">API</option>
            <option value="SYSTEM">SYSTEM</option>
          </select>
        </label>
        <label>
          Tipo de evento
          <select value={eventKind} onChange={(event) => { setEventKind(event.target.value); resetPage(); }}>
            <option value="all">Todos</option>
            <option value="administrative">Administrativos</option>
            <option value="security">Segurança</option>
          </select>
        </label>
        <label>
          Data inicial
          <input type="datetime-local" value={from} onChange={(event) => { setFrom(event.target.value); resetPage(); }} />
        </label>
        <label>
          Data final
          <input type="datetime-local" value={to} onChange={(event) => { setTo(event.target.value); resetPage(); }} />
        </label>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", margin: "10px 0 16px" }}>
        <button className="button ghost small" type="button" onClick={() => applyPreset("today")}>Hoje</button>
        <button className="button ghost small" type="button" onClick={() => applyPreset(24)}>Últimas 24h</button>
        <button className="button ghost small" type="button" onClick={() => applyPreset(24 * 7)}>7 dias</button>
        <button className="button ghost small" type="button" onClick={() => applyPreset(24 * 30)}>30 dias</button>
        <button className="button ghost small" type="button" disabled={activeFilters.length === 0} onClick={clearFilters}>Limpar filtros</button>
      </div>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 16 }}>
        <strong>{data.total} eventos encontrados</strong>
        {activeFilters.map((filter) => (
          <span key={filter} className="status-badge status-untested">{filter}</span>
        ))}
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="data-table-wrap">
        <table className="data-table" aria-label="Eventos de auditoria">
          <thead>
            <tr>
              <th scope="col">Data / evento</th>
              <th scope="col">Responsável</th>
              <th scope="col">Objeto afetado</th>
              <th scope="col">Alterações</th>
              <th scope="col">Origem</th>
              <th scope="col">Detalhe</th>
            </tr>
          </thead>
          <tbody>
            {busy ? (
              <tr><td colSpan={6}>Carregando histórico…</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={6}>Nenhum evento encontrado para os filtros atuais.</td></tr>
            ) : (
              data.items.map((item) => {
                const actor = actorLabel(item);
                const humanAction = actionLabels.get(item.action) || fallbackActionLabel(item.action);
                const humanModule = moduleLabels.get(item.module) || fieldLabel(item.module);
                const key = `${item.event_kind}:${item.id}`;
                return (
                  <Fragment key={key}>
                    <tr>
                      <td><strong>{humanAction}</strong><span>{formatDate(item.created_at)}</span></td>
                      <td><strong>{actor.name}</strong>{actor.email && <span>{actor.email}</span>}</td>
                      <td>
                        <strong>{item.entity.label || item.entity.id || "—"}</strong>
                        <span>{humanModule}{item.entity.id ? ` · ${item.entity.id}` : ""}</span>
                      </td>
                      <td><span>{changeSummary(item)}</span></td>
                      <td>
                        <strong>{item.source}</strong>
                        <span>{item.event_kind === "security" ? "Segurança" : "Administrativo"}</span>
                      </td>
                      <td>
                        <button className="button ghost small" type="button" onClick={() => setExpanded(expanded === key ? "" : key)}>
                          {expanded === key ? "Fechar" : "Ver detalhes"}
                        </button>
                      </td>
                    </tr>
                    {expanded === key && (
                      <tr>
                        <td colSpan={6}>
                          <EventDetail
                            item={item}
                            actionLabel={humanAction}
                            moduleLabel={humanModule}
                            onCorrelation={(value) => { setCorrelationId(value); resetPage(); }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="settings-pagination">
        <button className="button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Anterior</button>
        <span>{data.total} eventos · Página {Math.floor(offset / PAGE_SIZE) + 1}</span>
        <button className="button" disabled={busy || offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Próxima</button>
      </div>
    </>
  );
}
