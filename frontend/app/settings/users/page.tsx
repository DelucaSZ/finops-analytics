"use client";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
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
export default function UsersPage() {
  const locale = useLocale();
  const t = useTranslations("settings.users");
  const roles: Record<string, string> = { admin: t("roles.admin"), operator: t("roles.operator"), viewer: t("roles.viewer") };
  const titles: Record<Action, string> = {
    invite: t("actions.invite"), create: t("actions.create"), edit: t("actions.edit"),
    deactivate: t("actions.deactivate"), reactivate: t("actions.reactivate"), reset: t("actions.reset"),
    renew: t("actions.renew"), mfa: t("actions.mfa"), sessions: t("actions.sessions"),
  };
  const explanations: Partial<Record<Action, string>> = {
    deactivate: t("explanations.deactivate"), reactivate: t("explanations.reactivate"),
    reset: t("explanations.reset"), renew: t("explanations.renew"), mfa: t("explanations.mfa"),
  };
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
        err instanceof Error ? err.message : "ERR_USERS_ACTION",
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
          ? "USERS_LINK_GENERATED"
          : "USERS_UPDATED",
      );
      if (selfRevoked) router.replace("/login");
    });
  }
  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <>
            <button
              className="button primary"
              disabled={busy}
              onClick={() => open("invite")}
            >
              {t("actions.invite")}
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => open("create")}
            >
              {t("actions.create")}
            </button>
          </>
        }
      />
      <p className="settings-help">
        {t("rolesHelp")}
      </p>
      <IdentityProof />
      {error && (
        <p className="form-error" role="alert">
          {error === "ERR_USERS_ACTION" ? t("actionFailed") : error}
        </p>
      )}
      {message && (
        <p className="form-success" role="status">
          {message === "USERS_LINK_GENERATED" ? t("feedback.linkGenerated") : message === "USERS_UPDATED" ? t("feedback.updated") : message === "USERS_COPY_MANUAL" ? t("feedback.copyManual") : message === "USERS_LINK_COPIED" ? t("feedback.linkCopied") : message === "USERS_SESSIONS_REVOKED" ? t("feedback.sessionsRevoked") : message === "USERS_SESSION_REVOKED" ? t("feedback.sessionRevoked") : message}
        </p>
      )}
      {access && (
        <section className="security-card settings-panel">
          <h2>{t("accessLinkFor", {email: access.email})}</h2>
          <p>
            {t("linkExpires", {date: formatDate(access.expires_at, locale)})}
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
                    setMessage("USERS_COPY_MANUAL");
                    return;
                  }
                  await navigator.clipboard.writeText(access.url);
                  setMessage("USERS_LINK_COPIED");
                })
              }
            >
              {t("copyLink")}
            </button>
            <button className="button" onClick={() => setAccess(null)}>
              {t("hideLink")}
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
              {selected.id === me?.id ? t("yourAccount") : ""}
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
                  {t("refreshSessions")}
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
                        setMessage("USERS_SESSIONS_REVOKED");
                      }
                    })
                  }
                >
                  {t("endAllSessions")}
                </button>
              </div>
              {!sessionsLoaded ? (
                <p>{t("loadSessionsHint")}</p>
              ) : sessions.length === 0 ? (
                <p>{t("noSessions")}</p>
              ) : (
                sessions.map((item) => (
                  <article className="session-item" key={item.id}>
                    <div>
                      <strong>
                        {item.user_agent || t("unknownBrowser")}
                      </strong>
                      <p>
                        {t("sessionTimeline", {start: formatDate(item.created_at, locale), last: formatDate(item.last_seen_at, locale)})}
                      </p>
                      <p>{t("sessionExpires", {date: formatDate(item.expires_at, locale)})}</p>
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
                          setMessage("USERS_SESSION_REVOKED");
                        })
                      }
                    >
                      {t("endSession")}
                    </button>
                  </article>
                ))
              )}
              <button className="button" disabled={busy} onClick={close}>
                {t("close")}
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
                      {t("editWarning")}
                    </p>
                  )}
                </>
              )}
              {action === "invite" && (
                <p>
                  {t("inviteWarning")}
                </p>
              )}
              {(action === "create" || action === "mfa") && (
                <label>
                  {action === "create" ? t("initialPassword") : t("adminPassword")}
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
                  {busy ? t("saving") : action === "edit" ? t("saveChanges") : titles[action]}
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={busy}
                  onClick={close}
                >
                  {t("cancel")}
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
            <option value="">{t("status.all")}</option>
            <option value="active">{t("status.activePlural")}</option>
            <option value="pending">{t("status.pending")}</option>
            <option value="inactive">{t("status.inactivePlural")}</option>
          </select>
        </label>
        <button className="button" disabled={busy}>
          {t("search")}
        </button>
      </form>
      <div className="data-table-wrap">
        <table className="data-table settings-table">
          <thead>
            <tr>
              <th scope="col">{t("user")}</th>
              <th scope="col">{t("role")}</th>
              <th scope="col">{t("statusLabel")}</th>
              <th scope="col">MFA</th>
              <th scope="col">{t("columnActions")}</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={5}>{t("loading")}</td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan={5}>{t("empty")}</td>
              </tr>
            ) : (
              users.slice(0, 50).map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>
                      {user.name}
                      {user.id === me?.id ? t("self") : ""}
                    </strong>
                    <span>{user.email}</span>
                  </td>
                  <td>{roles[user.role] || user.role}</td>
                  <td>
                    {!user.is_active
                      ? t("status.inactive")
                      : user.password_set
                        ? t("status.active")
                        : t("status.pending")}
                  </td>
                  <td>
                    {user.mfa_enabled
                      ? t("mfa.enabled")
                      : user.mfa_reset_required
                        ? t("mfa.resetRequired")
                        : t("mfa.disabled")}
                  </td>
                  <td>
                    <div className="settings-row-actions">
                      <button
                        className="button"
                        disabled={busy}
                        onClick={() => open("edit", user)}
                      >
                        {t("edit")}
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
                        {user.is_active ? t("deactivate") : t("reactivate")}
                      </button>
                      {user.is_active && (
                        <button
                          className="button"
                          disabled={busy}
                          onClick={() =>
                            open(user.password_set ? "reset" : "renew", user)
                          }
                        >
                          {user.password_set ? t("recoverPassword") : t("renewInvitation")}
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
                        {t("sessions")}
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
                            {t("recoverMfa")}
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
          {t("previous")}
        </button>
        <span>{t("page", {page: offset / 50 + 1})}</span>
        <button
          className="button"
          disabled={loading || busy || users.length <= 50}
          onClick={() => {
            setOffset(offset + 50);
            close();
            setAccess(null);
          }}
        >
          {t("next")}
        </button>
      </div>
    </>
  );
}
