"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
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

function actionLabel(action: string, labels: Record<string, string>) {
  if (labels[action]) return labels[action];
  return action.split(".").map(fieldLabel).join(" · ");
}

type AuditPresentation = { yes: string; no: string; truncated: string; securityEvent: string; updatedItems: (count: number) => string; noDiff: string; unknownActor: string; unauthenticated: string };

function changeValue(value: unknown, words: AuditPresentation): string {
  if (value === null || value === undefined) return "∅";
  if (typeof value === "boolean") return value ? words.yes : words.no;
  if (typeof value === "string" || typeof value === "number") {
    const text = String(value);
    return text.length > 160 ? `${text.slice(0, 157)}…` : text;
  }
  if (Array.isArray(value)) {
    const text = value.map((item) => changeValue(item, words)).join(", ");
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

function changeSummary(item: Event, words: AuditPresentation): string {
  const entries = changeEntries(item);
  if (!entries.length) {
    if (item.changes?._truncated) return words.truncated;
    if (item.event_kind === "security") return item.reason || words.securityEvent;
    const updated = item.metadata?.updated;
    if (typeof updated === "number") return words.updatedItems(updated);
    return words.noDiff;
  }
  const head = entries
    .slice(0, 2)
    .map(([field, change]) => `${fieldLabel(field)}: ${changeValue(change.from, words)} → ${changeValue(change.to, words)}`)
    .join(" · ");
  return entries.length > 2 ? `${head} · +${entries.length - 2}` : head;
}

function actorLabel(item: Event, words: AuditPresentation): { name: string; email: string | null } {
  if (item.actor.name || item.actor.email) {
    return {
      name: item.actor.name || item.actor.email || words.unknownActor,
      email: item.actor.name ? item.actor.email : null,
    };
  }
  if (item.source === "SYSTEM") return { name: "SYSTEM", email: null };
  if (item.action === "auth.login_failed") return { name: words.unauthenticated, email: null };
  return { name: words.unknownActor, email: null };
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
  const locale = useLocale();
  const t = useTranslations("settings.audit");
  const words: AuditPresentation = {yes:t("presentation.yes"),no:t("presentation.no"),truncated:t("presentation.truncated"),securityEvent:t("presentation.securityEvent"),updatedItems:(count)=>t("presentation.updatedItems", {count}),noDiff:t("presentation.noDiff"),unknownActor:t("presentation.unknownActor"),unauthenticated:t("presentation.unauthenticated")};
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
        placeholder={t("nameOrEmail")}
        onFocus={() => setOpen(true)}
        onChange={(event) => onChange(event.target.value, "")}
      />
      {selectedId && <span>{t("selectedUser")}</span>}
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
  const locale = useLocale();
  const t = useTranslations("settings.audit");
  const words: AuditPresentation = {yes:t("presentation.yes"),no:t("presentation.no"),truncated:t("presentation.truncated"),securityEvent:t("presentation.securityEvent"),updatedItems:(count)=>t("presentation.updatedItems", {count}),noDiff:t("presentation.noDiff"),unknownActor:t("presentation.unknownActor"),unauthenticated:t("presentation.unauthenticated")};
  const localizedEvents: Record<string, string> = {
    "auth.login": t("events.authLogin"),
    "auth.login_failed": t("events.authLoginFailed"),
    "auth.logout": t("events.authLogout"),
    "auth.logout_all": t("events.authLogoutAll"),
    "auth.session_revoked": t("events.authSessionRevoked"),
    "auth.reauthenticated": t("events.authReauthenticated"),
    "auth.password_changed": t("events.authPasswordChanged"),
    "auth.password_reset": t("events.authPasswordReset"),
    "auth.invitation_accepted": t("events.authInvitationAccepted"),
    "user.created": t("events.userCreated"),
    "user.updated": t("events.userUpdated"),
    "user.invited": t("events.userInvited"),
    "user.invitation_renewed": t("events.userInvitationRenewed"),
    "user.password_reset_issued": t("events.userPasswordResetIssued"),
    "user.sessions_revoked": t("events.userSessionsRevoked"),
    "user.session_revoked": t("events.userSessionRevoked"),
    "user.create": t("events.userCreate"),
    "user.update": t("events.userUpdate"),
    "user.enable": t("events.userEnable"),
    "user.disable": t("events.userDisable"),
    "user.invite": t("events.userInvite"),
    "user.invitation_renew": t("events.userInvitationRenew"),
    "user.password_reset_issue": t("events.userPasswordResetIssue"),
    "user.sessions_revoke": t("events.userSessionsRevoke"),
    "user.mfa_reset": t("events.userMfaReset"),
    "mfa.setup_started": t("events.mfaSetupStarted"),
    "mfa.enabled": t("events.mfaEnabled"),
    "mfa.login_failed": t("events.mfaLoginFailed"),
    "mfa.login_verified": t("events.mfaLoginVerified"),
    "mfa.recovery_used": t("events.mfaRecoveryUsed"),
    "mfa.recovery_regenerated": t("events.mfaRecoveryRegenerated"),
    "mfa.reset": t("events.mfaReset"),
    "account.create": t("events.accountCreate"),
    "account.update": t("events.accountUpdate"),
    "account.enable": t("events.accountEnable"),
    "account.disable": t("events.accountDisable"),
    "account.delete": t("events.accountDelete"),
    "account.connection_test": t("events.accountConnectionTest"),
    "account.schedule_update": t("events.accountScheduleUpdate"),
    "policy.update": t("events.policyUpdate"),
    "policy.reset": t("events.policyReset"),
    "pricing.create": t("events.pricingCreate"),
    "pricing.update": t("events.pricingUpdate"),
    "pricing.override": t("events.pricingOverride"),
    "pricing.deactivate": t("events.pricingDeactivate"),
    "billing.profile_create": t("events.billingProfileCreate"),
    "billing.profile_update": t("events.billingProfileUpdate"),
    "tls.apply": t("events.tlsApply"),
    "tls.mode_change": t("events.tlsModeChange"),
    "opportunity.treat": t("events.opportunityTreat"),
    "opportunity.reject": t("events.opportunityReject"),
    "opportunity.reopen": t("events.opportunityReopen"),
    "opportunity.archive": t("events.opportunityArchive"),
    "opportunity.unarchive": t("events.opportunityUnarchive"),
    "opportunity.bulk_treat": t("events.opportunityBulkTreat"),
    "opportunity.bulk_reject": t("events.opportunityBulkReject"),
    "opportunity.bulk_reopen": t("events.opportunityBulkReopen"),
  };
  const modules: Array<readonly [string, string]> = [["",t("all")],["users",t("modules.users")],["security",t("modules.security")],["auth",t("modules.auth")],["mfa","MFA"],["accounts",t("modules.accounts")],["policies",t("modules.policies")],["opportunities",t("modules.opportunities")],["pricing",t("modules.pricing")],["billing","Billing"],["tls","HTTPS"]];
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
    .sort((a, b) => actionLabel(a, localizedEvents).localeCompare(actionLabel(b, localizedEvents)));

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
    actorQuery && t("filterActor", {value:actorQuery}),
    subjectQuery && t("filterSubject", {value:subjectQuery}),
    module && t("filterModule", {value:modules.find(([value]) => value === module)?.[1] || module}),
    action && t("filterAction", {value:actionLabel(action, localizedEvents)}),
    source && t("filterSource", {value:source}),
    eventKind !== "all" && t("filterKind", {value:eventKind === "security" ? t("security") : t("administrative")}),
    fromIso && t("filterFrom", {value:formatDate(fromIso, locale)}),
    toIso && t("filterTo", {value:formatDate(toIso, locale)}),
  ].filter(Boolean) as string[];

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={
          <button className="button" disabled={busy} onClick={() => setRefresh((value) => value + 1)}>
            {t("refresh")}
          </button>
        }
      />

      <p className="settings-help">
        {t("help")}
      </p>

      <div className="settings-filters">
        <UserAutocomplete
          label={t("actor")}
          query={actorQuery}
          selectedId={actorId}
          onChange={(value, id) => {
            setActorQuery(value);
            setActorId(id);
            resetPagination();
          }}
        />
        <UserAutocomplete
          label={t("subject")}
          query={subjectQuery}
          selectedId={subjectId}
          onChange={(value, id) => {
            setSubjectQuery(value);
            setSubjectId(id);
            resetPagination();
          }}
        />
        <label>
          {t("module")}
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
          {t("action")}
          <select value={action} onChange={(event) => { setAction(event.target.value); resetPagination(); }}>
            <option value="">{t("allFeminine")}</option>
            {availableActions.map((value) => (
              <option key={value} value={value}>{actionLabel(value, localizedEvents)}</option>
            ))}
          </select>
        </label>
        <label>
          {t("source")}
          <select value={source} onChange={(event) => { setSource(event.target.value); resetPagination(); }}>
            <option value="">{t("allFeminine")}</option>
            <option value="UI">UI</option>
            <option value="API">API</option>
            <option value="SYSTEM">SYSTEM</option>
          </select>
        </label>
        <label>
          {t("eventKind")}
          <select value={eventKind} onChange={(event) => { setEventKind(event.target.value); resetPagination(); }}>
            <option value="all">{t("all")}</option>
            <option value="administrative">{t("administrativePlural")}</option>
            <option value="security">{t("security")}</option>
          </select>
        </label>
        <label>
          {t("dateFrom")}
          <input
            type="date"
            value={fromIso ? fromIso.slice(0, 10) : ""}
            onChange={(event) => { setFromIso(localDateBoundary(event.target.value, false)); resetPagination(); }}
          />
        </label>
        <label>
          {t("dateTo")}
          <input
            type="date"
            value={toIso ? toIso.slice(0, 10) : ""}
            onChange={(event) => { setToIso(localDateBoundary(event.target.value, true)); resetPagination(); }}
          />
        </label>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-4)" }}>
        <button className="button" onClick={() => applyPreset(24)}>{t("last24h")}</button>
        <button className="button" onClick={() => applyPreset(24 * 7)}>{t("last7d")}</button>
        <button className="button" onClick={() => applyPreset(24 * 30)}>{t("last30d")}</button>
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
          {t("today")}
        </button>
        <button className="button" onClick={clearFilters}>{t("clear")}</button>
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-4)", alignItems: "center" }}>
        <strong>{t("totalEvents", {count:data.total})}</strong>
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
        <table className="data-table" aria-label={t("tableAria")}>
          <thead>
            <tr>
              <th scope="col">{t("dateTime")}</th>
              <th scope="col">{t("event")}</th>
              <th scope="col">{t("responsible")}</th>
              <th scope="col">{t("entity")}</th>
              <th scope="col">{t("changes")}</th>
              <th scope="col">{t("source")}</th>
            </tr>
          </thead>
          <tbody>
            {busy ? (
              <tr><td colSpan={6}>{t("loading")}</td></tr>
            ) : data.items.length === 0 ? (
              <tr><td colSpan={6}>{t("empty")}</td></tr>
            ) : (
              data.items.map((item) => {
                const actor = actorLabel(item, words);
                return (
                  <tr key={`${item.event_kind}:${item.id}`}>
                    <td><span>{formatDate(item.created_at, locale)}</span></td>
                    <td>
                      <strong>{actionLabel(item.action, localizedEvents)}</strong>
                      <span>{modules.find(([key]) => key === item.module)?.[1] || item.module} · {item.event_kind === "administrative" ? t("administrative") : t("security")}</span>
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
                      <span>{changeSummary(item, words)}</span>
                      <button className="button" onClick={() => setSelected(item)}>{t("details")}</button>
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
          {t("previous")}
        </button>
        <span>{t("pagination", {count:data.total, page:Math.floor(offset / PAGE_SIZE) + 1})}</span>
        <button className="button" disabled={busy || offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
          {t("next")}
        </button>
      </div>

      {selected && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={t("detailsAria")}
          style={{ position: "fixed", inset: 0, zIndex: 100, background: "var(--overlay)", display: "flex", justifyContent: "flex-end" }}
          onClick={() => setSelected(null)}
        >
          <section
            style={{ width: "min(720px, 100%)", height: "100%", overflowY: "auto", background: "var(--surface)", padding: "var(--space-6)" }}
            onClick={(event) => event.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-4)", alignItems: "flex-start" }}>
              <div>
                <span>{t("detailsHeading")}</span>
                <h2>{actionLabel(selected.action, localizedEvents)}</h2>
              </div>
              <button className="button" onClick={() => setSelected(null)}>{t("close")}</button>
            </div>
            <dl>
              <dt>{t("date")}</dt><dd>{formatDate(selected.created_at, locale)}</dd>
              <dt>{t("responsible")}</dt><dd>{actorLabel(selected, words).name}</dd>
              <dt>{t("responsibleEmail")}</dt><dd>{selected.actor.email || "—"}</dd>
              <dt>{t("module")}</dt><dd>{modules.find(([key]) => key === selected.module)?.[1] || selected.module}</dd>
              <dt>{t("source")}</dt><dd>{selected.source}</dd>
              <dt>{t("entity")}</dt><dd>{selected.entity.label || "—"}</dd>
              <dt>{t("entityId")}</dt><dd style={{ overflowWrap: "anywhere" }}>{selected.entity.id || "—"}</dd>
              <dt>Correlation ID</dt><dd style={{ overflowWrap: "anywhere" }}>{selected.correlation_id || "—"}</dd>
            </dl>

            <h3>{t("changes")}</h3>
            {changeEntries(selected).length ? (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead><tr><th>{t("field")}</th><th>{t("before")}</th><th>{t("after")}</th></tr></thead>
                  <tbody>
                    {changeEntries(selected).map(([field, change]) => (
                      <tr key={field}>
                        <td><strong>{fieldLabel(field)}</strong></td>
                        <td style={{ overflowWrap: "anywhere" }}>{changeValue(change.from, words)}</td>
                        <td style={{ overflowWrap: "anywhere" }}>{changeValue(change.to, words)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p>{selected.reason || t("noDiff")}</p>
            )}

            {Object.keys(selected.metadata || {}).length > 0 && (
              <>
                <h3>{t("safeContext")}</h3>
                <div className="data-table-wrap">
                  <table className="data-table">
                    <tbody>
                      {Object.entries(selected.metadata).map(([key, value]) => (
                        <tr key={key}><th>{fieldLabel(key)}</th><td style={{ overflowWrap: "anywhere" }}>{changeValue(value, words)}</td></tr>
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
