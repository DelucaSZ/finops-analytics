"use client";

import { useEffect, useState } from "react";
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
  correlation_id: string | null;
};

type Change = {
  from: unknown;
  to: unknown;
};

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
  "mfa.setup_started": "Cadastro do autenticador iniciado",
  "mfa.enabled": "Autenticador ativado ou substituído",
  "mfa.login_failed": "Segundo fator recusado",
  "mfa.login_verified": "Login com segundo fator concluído",
  "mfa.recovery_used": "Código de recuperação utilizado",
  "mfa.recovery_regenerated": "Códigos de recuperação regenerados",
  "mfa.reset": "MFA redefinido",
  "tls.apply": "Configuração HTTPS/TLS aplicada",
};

function fieldLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function changeValue(value: unknown): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value);
    return text.length > 120 ? `${text.slice(0, 117)}…` : text;
  }
  if (Array.isArray(value)) {
    const text = value.map((item) => changeValue(item)).join(", ");
    return text.length > 120 ? `${text.slice(0, 117)}…` : text || "[]";
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

function changeSummary(item: Event): string {
  const entries = changeEntries(item);
  if (!entries.length) {
    if (item.changes?._truncated) return "Alterações resumidas por limite de tamanho";
    return item.reason || "Sem alteração de campos";
  }
  const head = entries
    .slice(0, 2)
    .map(
      ([field, change]) =>
        `${fieldLabel(field)}: ${changeValue(change.from)} → ${changeValue(change.to)}`,
    )
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
  if (item.event_kind === "administrative" && item.source === "SYSTEM") {
    return { name: "SYSTEM", email: null };
  }
  if (item.action === "auth.login_failed") {
    return { name: "Tentativa não autenticada", email: null };
  }
  return { name: "Operador do host", email: null };
}

export default function AuditPage() {
  const [eventType, setEventType] = useState("all");
  const [module, setModule] = useState("");
  const [action, setAction] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState<{ items: Event[]; total: number }>({
    items: [],
    total: 0,
  });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setBusy(true);
    setError("");

    const query = new URLSearchParams({
      limit: "50",
      offset: String(offset),
      event_type: eventType,
    });
    if (module.trim()) query.set("module", module.trim());
    if (action.trim()) query.set("action", action.trim());

    api<{ items: Event[]; total: number }>(`/audit?${query}`, {
      signal: controller.signal,
    })
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [eventType, module, action, offset, refresh]);

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Auditoria"
        description="Histórico de segurança e alterações administrativas persistentes."
        actions={
          <button
            className="button"
            disabled={busy}
            onClick={() => setRefresh((value) => value + 1)}
          >
            Atualizar histórico
          </button>
        }
      />

      <p className="settings-help">
        Eventos administrativos preservam o nome e o e-mail do responsável no momento
        da ação. Senhas, tokens, chaves privadas e outros segredos não são armazenados
        na trilha de auditoria.
      </p>

      <div className="settings-filters">
        <label>
          Tipo de evento
          <select
            value={eventType}
            onChange={(event) => {
              setEventType(event.target.value);
              setOffset(0);
            }}
          >
            <option value="all">Todos</option>
            <option value="administrative">Administrativos</option>
            <option value="security">Segurança</option>
          </select>
        </label>
        <label>
          Módulo
          <input
            value={module}
            maxLength={80}
            placeholder="Ex.: users, tls, auth"
            onChange={(event) => {
              setModule(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Ação
          <input
            value={action}
            maxLength={120}
            placeholder="Ex.: user.update"
            onChange={(event) => {
              setAction(event.target.value);
              setOffset(0);
            }}
          />
        </label>
      </div>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="data-table-wrap">
        <table className="data-table" aria-label="Eventos de auditoria">
          <thead>
            <tr>
              <th scope="col">Data e ação</th>
              <th scope="col">Responsável</th>
              <th scope="col">Módulo</th>
              <th scope="col">Objeto afetado</th>
              <th scope="col">Alterações</th>
            </tr>
          </thead>
          <tbody>
            {busy ? (
              <tr>
                <td colSpan={5}>Carregando histórico…</td>
              </tr>
            ) : data.items.length === 0 ? (
              <tr>
                <td colSpan={5}>Nenhum evento encontrado.</td>
              </tr>
            ) : (
              data.items.map((item) => {
                const actor = actorLabel(item);
                const entries = changeEntries(item);
                return (
                  <tr key={`${item.event_kind}:${item.id}`}>
                    <td>
                      <strong>{labels[item.action] || item.action}</strong>
                      <span>{formatDate(item.created_at)}</span>
                    </td>
                    <td>
                      <strong>{actor.name}</strong>
                      {actor.email && <span>{actor.email}</span>}
                    </td>
                    <td>
                      <strong>{item.module}</strong>
                      <span>
                        {item.event_kind === "administrative"
                          ? `Administrativo · ${item.source}`
                          : "Segurança"}
                      </span>
                    </td>
                    <td>
                      <strong>{item.entity.label || item.entity.id || "—"}</strong>
                      <span>
                        {item.entity.type}
                        {item.entity.id ? ` · ${item.entity.id}` : ""}
                      </span>
                    </td>
                    <td>
                      <span>{changeSummary(item)}</span>
                      {entries.length > 0 && (
                        <details>
                          <summary>Ver alterações</summary>
                          <ul>
                            {entries.map(([field, change]) => (
                              <li key={field}>
                                <strong>{fieldLabel(field)}</strong>:{" "}
                                {changeValue(change.from)} → {changeValue(change.to)}
                              </li>
                            ))}
                          </ul>
                        </details>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="settings-pagination">
        <button
          className="button"
          disabled={busy || offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 50))}
        >
          Anterior
        </button>
        <span>
          {data.total} eventos · Página {offset / 50 + 1}
        </span>
        <button
          className="button"
          disabled={busy || offset + 50 >= data.total}
          onClick={() => setOffset(offset + 50)}
        >
          Próxima
        </button>
      </div>
    </>
  );
}
