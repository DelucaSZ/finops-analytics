"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CloudCog, LockKeyhole } from "lucide-react";
import { api } from "@/lib/api";

export function AccessForm({ mode }: { mode: "forgot" | "reset" | "invite" }) {
  const initialized = useRef("");
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(mode === "forgot");

  useEffect(() => {
    if (mode === "forgot" || initialized.current === mode) return;
    initialized.current = mode;
    const value = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    setToken(value);
    // Drop the bearer link from the current history entry after reading it into memory.
    window.history.replaceState(null, "", window.location.pathname);
    if (value.length !== 43) setError("Link inválido. Abra o link completo recebido ou solicite um novo.");
    setReady(true);
  }, [mode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode !== "forgot" && password !== confirm) { setError("As senhas não conferem."); return; }
    setLoading(true);
    try {
      const path = mode === "forgot" ? "/auth/forgot-password" : mode === "invite" ? "/auth/accept-invitation" : "/auth/reset-password";
      const result = await api<{ message: string }>(path, {
        method: "POST", body: JSON.stringify(mode === "forgot" ? { email } : { token, password }),
      });
      setMessage(result.message);
      setPassword(""); setConfirm(""); setToken("");
    } catch (err) { setError(err instanceof Error ? err.message : "Não foi possível concluir."); }
    finally { setLoading(false); }
  }

  return <main className="access-page"><section className="login-card">
    <div className="login-brand"><CloudCog size={28} /><span><strong>Deep</strong>Ops</span></div>
    <div className="login-icon"><LockKeyhole size={23} /></div>
    <h1>{mode === "forgot" ? "Recuperar acesso" : mode === "invite" ? "Ativar sua conta" : "Definir nova senha"}</h1>
    <p>{mode === "forgot" ? "Informe o e-mail da sua conta para solicitar a recuperação." : "Escolha uma senha de 12 a 128 caracteres. Após concluir, entre pela página de login."}</p>
    {message ? <p className="form-success" role="status">{message}</p> : <form onSubmit={submit}>
      {mode === "forgot" ? <label>E-mail<input type="email" autoComplete="email" maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} required /></label> : <>
        <label>Nova senha<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} required /></label>
        <label>Confirmar senha<input type="password" autoComplete="new-password" minLength={12} maxLength={128} value={confirm} onChange={(event) => setConfirm(event.target.value)} required /></label>
      </>}
      <button className="button primary full" disabled={!ready || loading || (mode !== "forgot" && token.length !== 43)}>{loading ? "Processando…" : mode === "forgot" ? "Solicitar recuperação" : "Salvar senha"}</button>
    </form>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <Link className="auth-link" href="/login">Voltar para o login</Link>
  </section></main>;
}
