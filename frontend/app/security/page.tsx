"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MfaSettings, MfaStatus } from "@/components/mfa-settings";
import { PageHeader } from "@/components/page-header";
import { api, formatDate } from "@/lib/api";

type Session = { id: string; created_at: string; last_seen_at: string; expires_at: string; user_agent: string; current: boolean };

export default function SecurityPage() {
  const router = useRouter();
  const [mfa, setMfa] = useState<MfaStatus | null>(null);
  const [passwordCode, setPasswordCode] = useState("");
  const [proofCode, setProofCode] = useState("");
  const [sessions, setSessions] = useState<Session[]>([]);
  const [password, setPassword] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [proof, setProof] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() { setSessions(await api<Session[]>("/auth/sessions")); setMfa(await api<MfaStatus>("/auth/mfa/status")); setLoaded(true); }
  useEffect(() => { load().catch((err) => setError(err.message)); }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await run(); } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível concluir."); }
    finally { setBusy(false); }
  }
  function changePassword(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) { setError("As senhas não conferem."); return; }
    action(async () => {
      await api("/auth/change-password", { method: "POST", body: JSON.stringify({ current_password: password, new_password: next, code: passwordCode }) });
      setPasswordCode(""); setPassword(""); setNext(""); setConfirm("");
      router.replace("/login");
    });
  }

  return <>
    <PageHeader eyebrow="CONTA" title="Minha segurança" description="Gerencie sua senha e os acessos à sua conta." />
    {error && <p className="form-error" role="alert">{error}</p>}
    {message && <p className="form-success" role="status">{message}</p>}
    <MfaSettings onStatusChange={setMfa} />
    <div className="security-grid">
      <section className="security-card"><h2>Alterar senha</h2><p>Ao salvar, todas as suas sessões serão encerradas. Entre novamente com a nova senha.</p>
        <form onSubmit={changePassword}>
          <label>Senha atual<input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
          <label>Nova senha<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={next} onChange={(event) => setNext(event.target.value)} required /></label>
          <label>Confirmar nova senha<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={confirm} onChange={(event) => setConfirm(event.target.value)} required /></label>
          <label>Código MFA ou de recuperação{!mfa?.enabled && " (se ativado)"}<input autoComplete="one-time-code" maxLength={64} value={passwordCode} onChange={e => setPasswordCode(e.target.value)} required={mfa?.enabled} /></label>
          <button className="button primary" disabled={busy}>Salvar senha</button>
        </form>
      </section>
      <section className="security-card"><h2>Confirmar identidade</h2><p>Confirme sua senha e o segundo fator, quando ativado, para autorizar ações administrativas sensíveis pelos próximos cinco minutos.</p>
        <form onSubmit={(event) => { event.preventDefault(); action(async () => {
          await api("/auth/reauthenticate", { method: "POST", body: JSON.stringify({ password: proof, code: proofCode }) });
          setProofCode(""); setProof(""); setMessage("Identidade confirmada por cinco minutos.");
        }); }}>
          <label>Sua senha<input type="password" autoComplete="current-password" value={proof} onChange={(event) => setProof(event.target.value)} required /></label>
          <label>Código MFA ou de recuperação{!mfa?.enabled && " (se ativado)"}<input autoComplete="one-time-code" maxLength={64} value={proofCode} onChange={e => setProofCode(e.target.value)} required={mfa?.enabled} /></label>
          <button className="button" disabled={busy}>Confirmar identidade</button>
        </form>
      </section>
    </div>
    <section className="security-card session-list"><h2>Sessões ativas</h2><p>As informações do navegador ajudam a reconhecer seus acessos.</p>
      <div className="security-actions"><button className="button" disabled={busy} onClick={() => action(load)}>Atualizar lista</button><button className="button" disabled={busy || !loaded} onClick={() => action(async () => {
        await api("/auth/logout-all", { method: "POST" }); router.replace("/login");
      })}>Encerrar todas, incluindo esta</button></div>
      {!loaded && <p>Carregando sessões…</p>}
      {sessions.map((session) => <article className="session-item" key={session.id}>
        <div><strong>{session.current ? "Esta sessão" : "Outro acesso"}</strong><p className="session-agent">{session.user_agent || "Navegador não identificado"}</p><p>Início: {formatDate(session.created_at)} · Última atividade: {formatDate(session.last_seen_at)}</p><p>Expira até: {formatDate(session.expires_at)}</p></div>
        <button className="button" disabled={busy} onClick={() => action(async () => {
          await api(`/auth/sessions/${session.id}`, { method: "DELETE" });
          if (session.current) router.replace("/login"); else await load();
        })}>{session.current ? "Sair desta sessão" : "Encerrar sessão"}</button>
      </article>)}
    </section>
  </>;
}
