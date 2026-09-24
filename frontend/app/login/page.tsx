"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CloudCog, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (challenge) {
        await api("/auth/mfa/verify", { method: "POST", body: JSON.stringify({ challenge, code }) });
        setChallenge(""); setCode(""); router.replace("/");
      } else {
        const result = await api<{ mfa_required?: boolean; challenge?: string; enrollment_required?: boolean }>("/auth/login", {
          method: "POST", body: JSON.stringify({ email, password }),
        });
        setPassword("");
        if (result.mfa_required && result.challenge) setChallenge(result.challenge);
        else router.replace(result.enrollment_required ? "/mfa-setup" : "/");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-visual">
        <div className="login-brand"><CloudCog size={28} /><span><strong>Deep</strong>Ops</span></div>
        <div className="login-copy">
          <span className="eyebrow">AWS FINOPS INTELLIGENCE</span>
          <h1>Encontre desperdícios.<br /><em>Decida com confiança.</em></h1>
          <p>Visibilidade multi-account, políticas adaptáveis e recomendações baseadas em evidências.</p>
        </div>
        <div className="orb orb-one" /><div className="orb orb-two" />
      </section>
      <section className="login-form-area">
        <form className="login-card" onSubmit={submit}>
          <div className="login-brand login-mobile-brand"><CloudCog size={28} /><span><strong>Deep</strong>Ops</span></div>
          <div className="login-icon"><LockKeyhole size={23} /></div>
          <h2>{challenge ? "Verificar segundo fator" : "Acessar plataforma"}</h2>
          {!challenge ? <>
          <p>Use o e-mail e a senha da sua conta DeepOps.</p>
          <label>E-mail<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <Link className="auth-link" href="/forgot-password">Esqueci minha senha</Link>
          </> : <>
            <p>{recovery ? "Informe um dos códigos de recuperação que você guardou. Cada código pode ser usado uma vez." : "Informe o código de seis dígitos do seu autenticador."}</p>
            <label>{recovery ? "Código de recuperação" : "Código do autenticador"}<input autoComplete="one-time-code" inputMode={recovery ? "text" : "numeric"} pattern={recovery ? undefined : "[0-9]{6}"} maxLength={recovery ? 64 : 6} value={code} onChange={e => setCode(e.target.value)} required autoFocus /></label>
            <button className="auth-link" type="button" onClick={() => { setRecovery(!recovery); setCode(""); setError(""); }}>{recovery ? "Usar autenticador" : "Usar código de recuperação"}</button>
            <button className="auth-link" type="button" onClick={() => { setChallenge(""); setCode(""); setError(""); setRecovery(false); }}>Voltar ao login</button>
          </>}
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="button primary full" disabled={loading}>
            {loading ? "Entrando…" : "Entrar"} <ArrowRight size={17} />
          </button>
        </form>
      </section>
    </main>
  );
}
