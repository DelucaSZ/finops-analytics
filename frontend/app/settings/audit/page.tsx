"use client";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";

type Event = {
  id: string;
  action: string;
  reason: string;
  created_at: string;
  actor_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  user_id: string;
  user_name: string;
  user_email: string;
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
  "mfa.setup_started": "Cadastro do autenticador iniciado",
  "mfa.enabled": "Autenticador ativado ou substituído",
  "mfa.login_failed": "Segundo fator recusado",
  "mfa.login_verified": "Login com segundo fator concluído",
  "mfa.recovery_used": "Código de recuperação utilizado",
  "mfa.recovery_regenerated": "Códigos de recuperação regenerados",
  "mfa.reset": "MFA redefinido",
};
export default function AuditPage() {
  const [category, setCategory] = useState("");
  const [userId, setUserId] = useState("");
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
    const query = new URLSearchParams({ limit: "50", offset: String(offset) });
    if (category) query.set("category", category);
    if (userId) query.set("user_id", userId);
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
  }, [category, userId, offset, refresh]);
  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Auditoria"
        description="Histórico de acessos, segundo fator e alterações administrativas."
        actions={
          <button
            className="button"
            disabled={busy}
            onClick={() => setRefresh((n) => n + 1)}
          >
            Atualizar histórico
          </button>
        }
      />
      <p className="settings-help">
        O histórico registra eventos a partir da implantação de cada recurso.
        Não contém senhas, códigos, segredos nem links de acesso. Os nomes e
        e-mails exibidos são os atuais do cadastro.
      </p>
      <div className="settings-filters">
        <label>
          Categoria
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">Todas</option>
            <option value="auth">Acessos e senha</option>
            <option value="user">Administração de usuários</option>
            <option value="mfa">Segundo fator</option>
          </select>
        </label>
        {userId && (
          <button
            className="button"
            onClick={() => {
              setUserId("");
              setOffset(0);
            }}
          >
            Remover filtro de usuário
          </button>
        )}
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Data e evento</th>
              <th scope="col">Responsável</th>
              <th scope="col">Conta afetada</th>
              <th scope="col">Detalhes</th>
            </tr>
          </thead>
          <tbody>
            {busy ? (
              <tr>
                <td colSpan={4}>Carregando histórico…</td>
              </tr>
            ) : data.items.length === 0 ? (
              <tr>
                <td colSpan={4}>Nenhum evento encontrado.</td>
              </tr>
            ) : (
              data.items.map((item) => (
                <tr key={item.id}>
                  <td>
                    <strong>{labels[item.action] || item.action}</strong>
                    <span>{formatDate(item.created_at)}</span>
                  </td>
                  <td>
                    {item.actor_id ? (
                      <>
                        <strong>{item.actor_name}</strong>
                        <span>{item.actor_email}</span>
                      </>
                    ) : item.action === "auth.login_failed" ? (
                      "Tentativa não autenticada"
                    ) : (
                      "Operador do host"
                    )}
                  </td>
                  <td>
                    <strong>{item.user_name}</strong>
                    <span>{item.user_email}</span>
                    <button
                      className="button"
                      onClick={() => {
                        setUserId(item.user_id);
                        setOffset(0);
                      }}
                    >
                      Filtrar esta conta
                    </button>
                  </td>
                  <td>{item.reason || "—"}</td>
                </tr>
              ))
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
