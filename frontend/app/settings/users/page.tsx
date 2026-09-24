"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "@/components/page-header";
import { IdentityProof } from "@/components/identity-proof";
import { api, ApiError, formatDate } from "@/lib/api";

type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  is_active: boolean;
  password_set: boolean;
  mfa_enabled: boolean;
  mfa_reset_required: boolean;
};
type Session = {
  id: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
};
type AccessLink = { url: string; expires_at: string };
type Action =
  | "invite"
  | "create"
  | "edit"
  | "deactivate"
  | "reactivate"
  | "reset"
  | "renew"
  | "mfa"
  | "sessions";
const roles: Record<string, string> = {
  admin: "Administrador",
  operator: "Operador",
  viewer: "Visualizador",
};
const titles: Record<Action, string> = {
  invite: "Convidar usuário",
  create: "Criar com senha",
  edit: "Editar usuário",
  deactivate: "Desativar usuário",
  reactivate: "Reativar usuário",
  reset: "Gerar recuperação de senha",
  renew: "Renovar convite",
  mfa: "Recuperar MFA",
  sessions: "Sessões do usuário",
};
const explanations: Partial<Record<Action, string>> = {
  deactivate:
    "O usuário perderá o acesso e suas sessões serão encerradas. O histórico será preservado.",
  reactivate:
    "O usuário poderá entrar novamente. As sessões antigas permanecem inválidas; usuários pendentes ainda precisam aceitar um convite válido.",
  reset:
    "Será gerado um link válido por 30 minutos. O link anterior de recuperação será invalidado. O MFA permanece ativo.",
  renew:
    "Será gerado um novo convite válido por 24 horas. O convite anterior será invalidado.",
  mfa: "Confirme a identidade do titular antes de prosseguir. O autenticador e códigos antigos serão removidos, as sessões encerradas e um novo cadastro será obrigatório. Confirme com SUA senha e segundo fator.",
};
export default function UsersPage() {
  const router = useRouter();
  const [users, setUsers] = useState<User[]>([]);
  const [me, setMe] = useState<User | null>(null);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [state, setState] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [action, setAction] = useState<Action | null>(null);
  const [selected, setSelected] = useState<User | null>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("viewer");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [access, setAccess] = useState<(AccessLink & { email: string }) | null>(
    null,
  );
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    const params = new URLSearchParams({
      limit: "51",
      offset: String(offset),
      q: query,
    });
    if (state) params.set("state", state);
    Promise.all([
      api<User[]>(`/users?${params}`, { signal: controller.signal }),
      api<User>("/auth/me", { signal: controller.signal }),
    ])
      .then(([items, current]) => {
        if (active) {
          setUsers(items);
          setMe(current);
        }
      })
      .catch((err) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [query, state, offset, refresh]);
  useEffect(() => {
    if (action) heading.current?.focus();
  }, [action, selected]);
  function open(next: Action, user: User | null = null) {
    setAction(next);
    setSelected(user);
    setName(user?.name || "");
    setEmail(user?.email || "");
    setRole(user?.role || "viewer");
    setPassword("");
    setCode("");
    setReason("");
    setAccess(null);
    setError("");
    setMessage("");
    setSessions([]);
    setSessionsLoaded(false);
  }
  function close() {
    setAction(null);
    setSelected(null);
    setPassword("");
    setCode("");
    setReason("");
  }
  async function run(task: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await task();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível concluir.",
      );
      if (err instanceof ApiError && err.detail === "reauthentication_required")
        document.getElementById("identity-proof")?.focus();
    } finally {
      setBusy(false);
    }
  }
  async function loadSessions(user: User) {
    setSessions(await api<Session[]>(`/users/${user.id}/sessions`));
    setSessionsLoaded(true);
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!action) return;
    run(async () => {
      let result: AccessLink | undefined;
      if (action === "invite")
        result = await api<AccessLink>("/users/invitations", {
          method: "POST",
          body: JSON.stringify({ name, email, role }),
        });
      else if (action === "create")
        await api("/users", {
          method: "POST",
          body: JSON.stringify({ name, email, role, password }),
        });
      else if (selected) {
        const path = `/users/${selected.id}`;
        if (action === "edit")
          await api(path, {
            method: "PATCH",
            body: JSON.stringify({ name, email, role }),
          });
        if (action === "deactivate" || action === "reactivate")
          await api(path, {
            method: "PATCH",
            body: JSON.stringify({ is_active: action === "reactivate" }),
          });
        if (action === "renew" || action === "reset")
          result = await api<AccessLink>(
            `${path}/${action === "renew" ? "invitation" : "password-reset"}`,
            { method: "POST" },
          );
        if (action === "mfa")
          await api(`/auth/mfa/reset/${selected.id}`, {
            method: "POST",
            body: JSON.stringify({ password, code, reason }),
          });
      }
      if (result)
        setAccess({
          ...result,
          url: new URL(result.url, window.location.origin).href,
          email: selected?.email || email,
        });
      const selfRevoked =
        selected !== null &&
        selected.id === me?.id &&
        (action === "deactivate" ||
          (action === "edit" &&
            (email.trim().toLowerCase() !== selected.email ||
              role !== selected.role)));
      close();
      setRefresh((n) => n + 1);
      setMessage(
        result
          ? "Link gerado. Compartilhe apenas com o titular por um canal privado."
          : "Alteração concluída.",
      );
      if (selfRevoked) router.replace("/login");
    });
  }
  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Usuários"
        description="Gerencie pessoas, permissões e recuperação de acesso."
        actions={
          <>
            <button
              className="button primary"
              disabled={busy}
              onClick={() => open("invite")}
            >
              Convidar usuário
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => open("create")}
            >
              Criar com senha
            </button>
          </>
        }
      />
      <p className="settings-help">
        Administrador: configura a plataforma e usuários. Operador: executa
        varreduras e trata oportunidades. Visualizador: consulta os dados.
      </p>
      <IdentityProof />
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {message && (
        <p className="form-success" role="status">
          {message}
        </p>
      )}
      {access && (
        <section className="security-card settings-panel">
          <h2>Link de acesso para {access.email}</h2>
          <p>
            Expira em {formatDate(access.expires_at)}. Nenhum e-mail foi enviado
            automaticamente.
          </p>
          <label>
            Link privado
            <input
              readOnly
              value={access.url}
              onFocus={(e) => e.target.select()}
            />
          </label>
          <div className="security-actions">
            <button
              className="button"
              onClick={() =>
                run(async () => {
                  if (!navigator.clipboard) {
                    setMessage("Selecione o link e copie manualmente.");
                    return;
                  }
                  await navigator.clipboard.writeText(access.url);
                  setMessage("Link copiado.");
                })
              }
            >
              Copiar link
            </button>
            <button className="button" onClick={() => setAccess(null)}>
              Ocultar link
            </button>
          </div>
        </section>
      )}
      {action && (
        <section className="security-card settings-panel">
          <h2 ref={heading} tabIndex={-1}>
            {titles[action]}
            {selected ? `: ${selected.name}` : ""}
          </h2>
          {selected && (
            <p>
              {selected.email}
              {selected.id === me?.id ? " · Sua conta" : ""}
            </p>
          )}
          {explanations[action] && <p>{explanations[action]}</p>}
          {action === "sessions" && selected ? (
            <>
              <div className="security-actions">
                <button
                  className="button"
                  disabled={busy}
                  onClick={() => run(() => loadSessions(selected))}
                >
                  Atualizar sessões
                </button>
                <button
                  className="button"
                  disabled={busy || !sessionsLoaded || sessions.length === 0}
                  onClick={() =>
                    run(async () => {
                      await api(`/users/${selected.id}/sessions`, {
                        method: "DELETE",
                      });
                      if (selected.id === me?.id) router.replace("/login");
                      else {
                        await loadSessions(selected);
                        setMessage("Todas as sessões foram encerradas.");
                      }
                    })
                  }
                >
                  Encerrar todas as sessões
                </button>
              </div>
              {!sessionsLoaded ? (
                <p>Carregue a lista para consultar os acessos.</p>
              ) : sessions.length === 0 ? (
                <p>Nenhuma sessão ativa.</p>
              ) : (
                sessions.map((item) => (
                  <article className="session-item" key={item.id}>
                    <div>
                      <strong>
                        {item.user_agent || "Navegador não identificado"}
                      </strong>
                      <p>
                        Início: {formatDate(item.created_at)} · Última
                        atividade: {formatDate(item.last_seen_at)}
                      </p>
                      <p>Expira até: {formatDate(item.expires_at)}</p>
                    </div>
                    <button
                      className="button"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          await api(
                            `/users/${selected.id}/sessions/${item.id}`,
                            { method: "DELETE" },
                          );
                          await loadSessions(selected);
                          setMessage("Sessão encerrada.");
                        })
                      }
                    >
                      Encerrar sessão
                    </button>
                  </article>
                ))
              )}
              <button className="button" disabled={busy} onClick={close}>
                Fechar
              </button>
            </>
          ) : (
            <form onSubmit={submit}>
              {["invite", "create", "edit"].includes(action) && (
                <>
                  <div className="settings-inline-form">
                    <label>
                      Nome
                      <input
                        maxLength={120}
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                      />
                    </label>
                    <label>
                      E-mail
                      <input
                        type="email"
                        maxLength={254}
                        autoComplete="off"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        required
                      />
                    </label>
                    <label>
                      Perfil
                      <select
                        value={role}
                        onChange={(e) => setRole(e.target.value)}
                      >
                        {Object.entries(roles).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  {action === "edit" && (
                    <p>
                      Alterar e-mail ou perfil encerra as sessões e invalida
                      links pendentes. Se for sua conta, você precisará entrar
                      novamente.
                    </p>
                  )}
                </>
              )}
              {action === "invite" && (
                <p>
                  O convite vale por 24 horas e permite ao titular definir a
                  própria senha. Você receberá o link para compartilhar em
                  privado.
                </p>
              )}
              {(action === "create" || action === "mfa") && (
                <label>
                  {action === "create"
                    ? "Senha inicial (mínimo de 12 caracteres)"
                    : "Sua senha de administrador"}
                  <input
                    type="password"
                    autoComplete={
                      action === "create" ? "new-password" : "current-password"
                    }
                    minLength={action === "create" ? 12 : 1}
                    maxLength={action === "create" ? 128 : 1024}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </label>
              )}
              {action === "mfa" && (
                <>
                  <label>
                    Seu código MFA ou de recuperação
                    <input
                      autoComplete="one-time-code"
                      maxLength={64}
                      value={code}
                      onChange={(e) => setCode(e.target.value)}
                      required
                    />
                  </label>
                  <label>
                    Motivo ou chamado de recuperação
                    <textarea
                      minLength={10}
                      maxLength={500}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      required
                    />
                  </label>
                </>
              )}
              <div className="security-actions">
                <button className="button primary" disabled={busy}>
                  {busy
                    ? "Salvando…"
                    : action === "edit"
                      ? "Salvar alterações"
                      : titles[action]}
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={busy}
                  onClick={close}
                >
                  Cancelar
                </button>
              </div>
            </form>
          )}
        </section>
      )}
      <form
        className="settings-filters"
        onSubmit={(e) => {
          e.preventDefault();
          close();
          setAccess(null);
          setOffset(0);
          setQuery(q);
          setRefresh((n) => n + 1);
        }}
      >
        <label>
          Buscar por nome ou e-mail
          <input
            maxLength={254}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label>
          Situação
          <select
            value={state}
            onChange={(e) => {
              setState(e.target.value);
              setOffset(0);
              close();
              setAccess(null);
            }}
          >
            <option value="">Todas</option>
            <option value="active">Ativos</option>
            <option value="pending">Convite pendente</option>
            <option value="inactive">Inativos</option>
          </select>
        </label>
        <button className="button" disabled={busy}>
          Buscar
        </button>
      </form>
      <div className="data-table-wrap">
        <table className="data-table settings-table">
          <thead>
            <tr>
              <th scope="col">Usuário</th>
              <th scope="col">Perfil</th>
              <th scope="col">Situação</th>
              <th scope="col">MFA</th>
              <th scope="col">Ações</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5}>Carregando usuários…</td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={5}>Nenhum usuário encontrado.</td>
              </tr>
            ) : (
              users.slice(0, 50).map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>
                      {user.name}
                      {user.id === me?.id ? " (você)" : ""}
                    </strong>
                    <span>{user.email}</span>
                  </td>
                  <td>{roles[user.role]}</td>
                  <td>
                    {!user.is_active
                      ? "Inativo"
                      : user.password_set
                        ? "Ativo"
                        : "Convite pendente"}
                  </td>
                  <td>
                    {user.mfa_enabled
                      ? "Ativado"
                      : user.mfa_reset_required
                        ? "Novo cadastro obrigatório"
                        : "Não ativado"}
                  </td>
                  <td>
                    <div className="settings-row-actions">
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => open("edit", user)}
                      >
                        Editar
                      </button>
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() =>
                          open(
                            user.is_active ? "deactivate" : "reactivate",
                            user,
                          )
                        }
                      >
                        {user.is_active ? "Desativar" : "Reativar"}
                      </button>
                      {user.is_active && (
                        <button
                          className="button"
                          disabled={busy}
                          onClick={() =>
                            open(user.password_set ? "reset" : "renew", user)
                          }
                        >
                          {user.password_set
                            ? "Recuperar senha"
                            : "Renovar convite"}
                        </button>
                      )}
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => {
                          open("sessions", user);
                          run(() => loadSessions(user));
                        }}
                      >
                        Sessões
                      </button>
                      {user.is_active &&
                        user.password_set &&
                        user.id !== me?.id &&
                        user.mfa_enabled && (
                          <button
                            className="button"
                            disabled={busy}
                            onClick={() => open("mfa", user)}
                          >
                            Recuperar MFA
                          </button>
                        )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="settings-pagination">
        <button
          className="button"
          disabled={loading || busy || offset === 0}
          onClick={() => {
            setOffset(Math.max(0, offset - 50));
            close();
            setAccess(null);
          }}
        >
          Anterior
        </button>
        <span>Página {offset / 50 + 1}</span>
        <button
          className="button"
          disabled={loading || busy || users.length <= 50}
          onClick={() => {
            setOffset(offset + 50);
            close();
            setAccess(null);
          }}
        >
          Próxima
        </button>
      </div>
    </>
  );
}
