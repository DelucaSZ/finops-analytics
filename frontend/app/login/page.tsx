"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, CloudCog, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      router.replace("/");
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
          <h2>Acessar plataforma</h2>
          <p>Use o e-mail e a senha da sua conta DeepOps.</p>
          <label>E-mail<input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
          <label>Senha<input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
          <Link className="auth-link" href="/forgot-password">Esqueci minha senha</Link>
          {error && <div className="form-error">{error}</div>}
          <button className="button primary full" disabled={loading}>
            {loading ? "Entrando…" : "Entrar"} <ArrowRight size={17} />
          </button>
        </form>
      </section>
    </main>
  );
}
