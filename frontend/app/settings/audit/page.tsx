"use client";

import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";

type Actor = { id: string | null; name: string | null; email: string | null };
type Entity = { type: string; id: string | null; label: string | null };
type UserOption = { id: string; name: string; email: string };
type Change = { from: unknown; to: unknown };

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
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  changes: Record<string, unknown>;
  metadata: Record<string, unknown>;
  correlation_id: string | null;
};

const PAGE_SIZE = 50;

const labels: Record<string, string> = {
  "auth.login": "Login concluído",
  "auth.login_failed": "Tentativa de login recusada",
  "auth.logout": "Saída da conta",
  "auth.logout_all": "Todas as sessões encerradas",
  "auth.session_revoked": "Sessão encerrada pelo titular",
  "auth.reauthenticated": "Identidade confirmada",
  "auth.password_changed": "Senha alterada",
  "auth.password_reset": "Senha redefinida",
  "auth.invitation_accepted": "Convite aceito",
  "user.created": "Usuário criado",
  "user.updated": "Cadastro alterado",
  "user.invited": "Usuário convidado",
  "user.invitation_renewed": "Convite renovado",
  "user.password_reset_issued": "Link de recuperação gerado",
  "user.sessions_revoked": "Sessões encerradas por administrador",
  "user.session_revoked": "Sessão encerrada por administrador",
  "user.create": "Usuário criado",
  "user.update": "Usuário alterado",
  "user.enable": "Usuário ativado",
  "user.disable": "Usuário desativado",
  "user.invite": "Usuário convidado",
  "user.invitation_renew": "Convite renovado",
  "user.password_reset_issue": "Reset administrativo de senha emitido",
  "user.sessions_revoke": "Sessões de usuário revogadas",
  "user.mfa_reset": "MFA de usuário redefinido",
  "mfa.setup_started": "Cadastro do autenticador iniciado",
  "mfa.enabled": "Autenticador ativado ou substituído",
  "mfa.login_failed": "Segundo fator recusado",
  "mfa.login_verified": "Login com segundo fator concluído",
  "mfa.recovery_used": "Código de recuperação utilizado",
  "mfa.recovery_regenerated": "Códigos de recuperação regenerados",
  "mfa.reset": "MFA redefinido",
  "account.create": "Conta cloud criada",
  "account.update": "Conta cloud alterada",
  "account.enable": "Conta cloud ativada",
  "account.disable": "Conta cloud desativada",
  "account.delete": "Conta cloud removida",
  "account.connection_test": "Conexão da conta testada",
  "account.schedule_update": "Agenda de coleta alterada",
  "policy.update": "Policy alterada",
  "policy.reset": "Policy restaurada para o padrão",
  "pricing.create": "Preço criado",
  "pricing.update": "Preço alterado",
  "pricing.override": "Nova versão de preço criada",
  "pricing.deactivate": "Preço desativado",
  "billing.profile_create": "Perfil de Billing criado",
  "billing.profile_update": "Perfil de Billing alterado",
  "tls.apply": "Configuração HTTPS/TLS aplicada",
  "tls.mode_change": "Modo HTTPS/TLS alterado",
  "opportunity.treat": "Oportunidade tratada",
  "opportunity.reject": "Oportunidade rejeitada",
  "opportunity.reopen": "Oportunidade reaberta",
  "opportunity.archive": "Oportunidade arquivada",
  "opportunity.unarchive": "Oportunidade desarquivada",
  "opportunity.bulk_treat": "Oportunidades tratadas em massa",
  "opportunity.bulk_reject": "Oportunidades rejeitadas em massa",
  "opportunity.bulk_reopen": "Oportunidades reabertas em massa",
};

const modules = [
  ["", "Todos"],
  ["users", "Usuários"],
  ["security", "Segurança"],
  ["auth", "Acessos"],
  ["mfa", "MFA"],
  ["accounts", "Contas"],
  ["policies", "Policies"],
  ["opportunities", "Oportunidades"],
  ["pricing", "Pricing"],
  ["billing", "Billing"],
  ["tls", "HTTPS"],
] as const;

const actionModule: Record<string, string> = {
  "user.create": "users",
  "user.update": "users",
  "user.enable": "users",
  "user.disable": "users",
  "user.invite": "users",
  "user.invitation_renew": "users",
  "user.password_reset_issue": "users",
  "user.sessions_revoke": "users",
  "user.mfa_reset": "users",
  "account.create": "accounts",
  "account.update": "accounts",
  "account.enable": "accounts",
  "account.disable": "accounts",
  "account.delete": "accounts",
  "account.connection_test": "accounts",
  "account.schedule_update": "accounts",
  "policy.update": "policies",
  "policy.reset": "policies",
  "pricing.create": "pricing",
  "pricing.update": "pricing",
  "pricing.override": "pricing",
  "pricing.deactivate": "pricing",
  "billing.profile_create": "billing",
  "billing.profile_update": "billing",
  "tls.apply": "tls",
  "tls.mode_change": "tls",
  "opportunity.treat": "opportunities",
  "opportunity.reject": "opportunities",
  "opportunity.reopen": "opportunities",
  "opportunity.archive": "opportunities",
  "opportunity.unarchive": "opportunities",
  "opportunity.bulk_treat": "opportunities",
  "opportunity.bulk_reject": "opportunities",
  "opportunity.bulk_reopen": "opportunities",
};

function fieldLabel(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function actionLabel(action: string) {
  if (labels[action]) return labels[action];
  return action.split(".").map(fieldLabel).join(" · ");
}

function changeValue(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value);
    return text.length > 160 ? `${text.slice(0, 157)}…` : text;
  }
  if (Array.isArray(value)) {
    const text = value.map((item) => changeValue(item)).join(", ");
    return text.length > 160 ? `${text.slice(0, 157)}…` : text || "[]";
  }
  const text = JSON.stringify(value);
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
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

function changeSummary(item: Event): string {
  const entries = changeEntries(item);
  if (!entries.length) {
    if (item.changes?._truncated) return "Alterações resumidas por limite de tamanho";
    if (item.event_kind === "security") return item.reason || "Evento de segurança";
    const updated = item.metadata?.updated;
    if (typeof updated === "number") return `${updated} itens alterados`;
    return "Ação sem diff de campos";
  }
  const head = entries
    .slice(0, 2)
    .map(([field, change]) => `${fieldLabel(field)}: ${changeValue(change.from)} → ${changeValue(change.to)}`)
    .join(" · ");
  return entries.length > 2 ? `${head} · +${entries.length - 2}` : head;
}

function actorLabel(item: Event): { name: string; email: string | null } {
  if (item.actor.name || item.actor.email) {
    return {
      name: item.actor.name || item.actor.email || "Responsável desconhecido",
      email: item.actor.name ? item.actor.email : null,
    };
  }
  if (item.source === "SYSTEM") return { name: "SYSTEM", email: null };
  if (item.action === "auth.login_failed") return { name: "Tentativa não autenticada", email: null };
  return { name: "Responsável desconhecido", email: null };
}

function localDateBoundary(date: string, end: boolean) {
  if (!date) return "";
  const value = new Date(`${date}T${end ? "23:59:59.999" : "00:00:00.000"}`);
  return value.toISOString();
}

function UserAutocomplete({
  label,
  query,
  selectedId,
  onChange,
}: {
  label: string;
  query: string;
  selectedId: string;
  onChange: (query: string, id: string) => void;
}) {
  const [options, setOptions] = useState<UserOption[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (selectedId || query.trim().length < 2) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      api<UserOption[]>(`/audit/users?q=${encodeURIComponent(query.trim())}&limit=20`, {
        signal: controller.signal,
      })
        .then((items) => {
          setOptions(items);
          setOpen(true);
        })
        .catch(() => setOptions([]));
    }, 300);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, selectedId]);

  return (
    <label style={{ position: "relative" }}>
      {label}
      <input
        value={query}
        maxLength={254}
        placeholder="Nome ou e-mail"
        onFocus={() => setOpen(true)}
        onChange={(event) => onChange(event.target.value, "")}
      />
      {selectedId && <span>Usuário selecionado</span>}
      {open && !selectedId && options.length > 0 && (
        <div
          role="listbox"
          style={{
            position: "absolute",
            zIndex: 20,
            top: "100%",
            left: 0,
            right: 0,
            maxHeight: 240,
            overflowY: "auto",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius-control)",
            background: "var(--surface)",
            boxShadow: "var(--shadow)",
            padding: "var(--space-2)",
          }}
        >
          {options.map((option) => (
            <button
              type="button"
              key={option.id}
              role="option"
              aria-selected={option.id === selectedId}
              className="button"
              style={{ width: "100%", textAlign: "left", marginBottom: "var(--space-1)" }}
              onClick={() => {
                onChange(`${option.name} — ${option.email}`, option.id);
                setOpen(false);
              }}
            >
              <strong>{option.name}</strong> · {option.email}
            </button>
          ))}
        </div>
      )}
    </label>
  );
}

export default function AuditPage() {
  const initial = useMemo(() => {
    if (typeof window === "undefined") return new URLSearchParams();
    return new URLSearchParams(window.location.search);
  }, []);
  const [eventKind, setEventKind] = useState(initial.get("event_kind") || "all");
  const [actorQuery, setActorQuery] = useState(initial.get("actor_search") || "");
  const [actorId, setActorId] = useState(initial.get("actor_id") || "");
  const [subjectQuery, setSubjectQuery] = useState(initial.get("subject_user_search") || "");
  const [subjectId, setSubjectId] = useState(initial.get("subject_user_id") || "");
  const [module, setModule] = useState(initial.get("module") || "");
  const [action, setAction] = useState(initial.get("action") || "");
  const [source, setSource] = useState(initial.get("source") || "");
  const [fromIso, setFromIso] = useState(initial.get("from") || "");
  const [toIso, setToIso] = useState(initial.get("to") || "");
  const [offset, setOffset] = useState(Number(initial.get("offset") || 0));
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{ items: Event[]; total: number }>({ items: [], total: 0 });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Event | null>(null);

  const availableActions = Object.keys(actionModule)
    .filter((key) => !module || actionModule[key] === module)
    .sort((a, b) => actionLabel(a).localeCompare(actionLabel(b)));

  const query = useMemo(() => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
      event_kind: eventKind,
    });
    if (actorId) params.set("actor_id", actorId);
    else if (actorQuery.trim()) params.set("actor_search", actorQuery.trim());
    if (subjectId) params.set("subject_user_id", subjectId);
    else if (subjectQuery.trim()) params.set("subject_user_search", subjectQuery.trim());
    if (module) params.set("module", module);
    if (action) params.set("action", action);
    if (source) params.set("source", source);
    if (fromIso) params.set("from", fromIso);
    if (toIso) params.set("to", toIso);
    return params;
  }, [eventKind, actorId, actorQuery, subjectId, subjectQuery, module, action, source, fromIso, toIso, offset]);

  useEffect(() => {
    const visible = new URLSearchParams(query);
    visible.delete("limit");
    if (visible.get("offset") === "0") visible.delete("offset");
    window.history.replaceState(null, "", `${window.location.pathname}${visible.size ? `?${visible}` : ""}`);
  }, [query]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setError("");
    api<{ items: Event[]; total: number }>(`/audit?${query}`, { signal: controller.signal })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        if (active && err.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [query, refresh]);

  function resetPagination() {
    setOffset(0);
  }

  function applyPreset(hours: number) {
    const now = new Date();
    const start = new Date(now.getTime() - hours * 60 * 60 * 1000);
    setFromIso(start.toISOString());
    setToIso(now.toISOString());
    resetPagination();
  }

  function clearFilters() {
    setEventKind("all");
    setActorQuery("");
    setActorId("");
    setSubjectQuery("");
    setSubjectId("");
    setModule("");
    setAction("");
    setSource("");
    setFromIso("");
    setToIso("");
    setOffset(0);
  }

  const activeFilters = [
    actorQuery && `Executado por: ${actorQuery}`,
    subjectQuery && `Usuário afetado: ${subjectQuery}`,
    module && `Módulo: ${modules.find(([value]) => value === module)?.[1] || module}`,
    action && `Ação: ${actionLabel(action)}`,
    source && `Origem: ${source}`,
    eventKind !== "all" && `Tipo: ${eventKind === "security" ? "Segurança" : "Administrativo"}`,
    fromIso && `Desde: ${formatDate(fromIso)}`,
    toIso && `Até: ${formatDate(toIso)}`,
  ].filter(Boolean) as string[];

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
        O responsável é exibido pelo snapshot registrado no momento do evento. Senhas, tokens,
        chaves privadas e outros segredos são removidos antes da persistência.
      </p>

      <div className="settings-filters">
        <UserAutocomplete
          label="Executado por"
          query={actorQuery}
          selectedId={actorId}
          onChange={(value, id) => {
            setActorQuery(value);
            setActorId(id);
            resetPagination();
          }}
        />
        <UserAutocomplete
          label="Usuário afetado"
          query={subjectQuery}
          selectedId={subjectId}
          onChange={(value, id) => {
            setSubjectQuery(value);
            setSubjectId(id);
            resetPagination();
          }}
        />
        <label>
          Módulo
          <select
            value={module}
            onChange={(event) => {
              const value = event.target.value;
              setModule(value);
              if (action && value && actionModule[action] !== value) setAction("");
              resetPagination();
            }}
          >
            {modules.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label>
          Ação
          <select value={action} onChange={(event) => { setAction(event.target.value); resetPagination(); }}>
            <option value="">Todas</option>
            {availableActions.map((value) => (
              <option key={value} value={value}>{actionLabel(value)}</option>
            ))}
          </select>
        </label>
        <label>
          Origem
          <select value={source} onChange={(event) => { setSource(event.target.value); resetPagination(); }}>
            <option value="">Todas</option>
            <option value="UI">UI</option>
            <option value="API">API</option>
            <option value="SYSTEM">SYSTEM</option>
          </select>
        </label>
        <label>
          Tipo de evento
          <select value={eventKind} onChange={(event) => { setEventKind(event.target.value); resetPagination(); }}>
            <option value="all">Todos</option>
            <option value="administrative">Administrativos</option>
            <option value="security">Segurança</option>
          </select>
        </label>
        <label>
          Data inicial
          <input
            type="date"
            value={fromIso ? fromIso.slice(0, 10) : ""}
            onChange={(event) => { setFromIso(localDateBoundary(event.target.value, false)); resetPagination(); }}
          />
        </label>
        <label>
          Data final
          <input
            type="date"
            value={toIso ? toIso.slice(0, 10) : ""}
            onChange={(event) => { setToIso(localDateBoundary(event.target.value, true)); resetPagination(); }}
          />
        </label>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
        <button className="button" onClick={() => applyPreset(24)}>Últimas 24h</button>
        <button className="button" onClick={() => applyPreset(24 * 7)}>7 dias</button>
        <button className="button" onClick={() => applyPreset(24 * 30)}>30 dias</button>
        <button
          className="button"
          onClick={() => {
            const now = new Date();
            const start = new Date(now);
            start.setHours(0, 0, 0, 0);
            setFromIso(start.toISOString());
            setToIso(now.toISOString());
            resetPagination();
          }}
        >
          Hoje
        </button>
        <button className="button" onClick={clearFilters}>Limpar filtros</button>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-4)", alignItems: "center" }}>
        <strong>{data.total} eventos encontrados</strong>
        {activeFilters.map((filter) => (
          <span
            key={filter}
            style={{
              padding: "var(--space-1) var(--space-2)",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-pill)",
            }}
          >
            {filter}
          </span>
        ))}
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}

      <div className="data-table-wrap">
        <table className="data-table" aria-label="Eventos de auditoria">
          <thead>
            <tr>
              <th scope="col">Data/hora</th>
              <th scope="col">Evento</th>
              <th scope="col">Responsável</th>
              <th scope="col">Objeto afetado</th>
              <th scope="col">Alterações</th>
              <th scope="col">Origem</th>
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
                return (
                  <tr key={`${item.event_kind}:${item.id}`}>
                    <td><span>{formatDate(item.created_at)}</span></td>
                    <td>
                      <strong>{actionLabel(item.action)}</strong>
                      <span>{item.module} · {item.event_kind === "administrative" ? "Administrativo" : "Segurança"}</span>
                    </td>
                    <td>
                      <strong>{actor.name}</strong>
                      {actor.email && <span>{actor.email}</span>}
                    </td>
                    <td>
                      <strong>{item.entity.label || item.entity.id || "—"}</strong>
                      <span>{item.entity.type}{item.entity.id ? ` · ${item.entity.id}` : ""}</span>
                    </td>
                    <td>
                      <span>{changeSummary(item)}</span>
                      <button className="button" onClick={() => setSelected(item)}>Ver detalhes</button>
                    </td>
                    <td><strong>{item.source}</strong></td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="settings-pagination">
        <button className="button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
          Anterior
        </button>
        <span>{data.total} eventos · Página {Math.floor(offset / PAGE_SIZE) + 1}</span>
        <button className="button" disabled={busy || offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          Próxima
        </button>
      </div>

      {selected && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Detalhes do evento de auditoria"
          style={{ position: "fixed", inset: 0, zIndex: 100, background: "var(--overlay)", display: "flex", justifyContent: "flex-end" }}
          onClick={() => setSelected(null)}
        >
          <section
            style={{ width: "min(720px, 100%)", height: "100%", overflowY: "auto", background: "var(--surface)", padding: "var(--space-6)" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-4)", alignItems: "flex-start" }}>
              <div>
                <span>DETALHE DO EVENTO</span>
                <h2>{actionLabel(selected.action)}</h2>
              </div>
              <button className="button" onClick={() => setSelected(null)}>Fechar</button>
            </div>
            <dl>
              <dt>Data</dt><dd>{formatDate(selected.created_at)}</dd>
              <dt>Responsável</dt><dd>{actorLabel(selected).name}</dd>
              <dt>E-mail do responsável</dt><dd>{selected.actor.email || "—"}</dd>
              <dt>Módulo</dt><dd>{selected.module}</dd>
              <dt>Origem</dt><dd>{selected.source}</dd>
              <dt>Objeto afetado</dt><dd>{selected.entity.label || "—"}</dd>
              <dt>ID da entidade</dt><dd style={{ overflowWrap: "anywhere" }}>{selected.entity.id || "—"}</dd>
              <dt>Correlation ID</dt><dd style={{ overflowWrap: "anywhere" }}>{selected.correlation_id || "—"}</dd>
            </dl>

            <h3>Alterações</h3>
            {changeEntries(selected).length ? (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead><tr><th>Campo</th><th>Antes</th><th>Depois</th></tr></thead>
                  <tbody>
                    {changeEntries(selected).map(([field, change]) => (
                      <tr key={field}>
                        <td><strong>{fieldLabel(field)}</strong></td>
                        <td style={{ overflowWrap: "anywhere" }}>{changeValue(change.from)}</td>
                        <td style={{ overflowWrap: "anywhere" }}>{changeValue(change.to)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>{selected.reason || "Este evento é semântico e não possui diff de campos."}</p>
            )}

            {Object.keys(selected.metadata || {}).length > 0 && (
              <>
                <h3>Contexto seguro</h3>
                <div className="data-table-wrap">
                  <table className="data-table">
                    <tbody>
                      {Object.entries(selected.metadata).map(([key, value]) => (
                        <tr key={key}><th>{fieldLabel(key)}</th><td style={{ overflowWrap: "anywhere" }}>{changeValue(value)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
