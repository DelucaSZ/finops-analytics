"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { MfaSettings, MfaStatus } from "@/components/mfa-settings";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";

export default function SecurityPage() {
  const router = useRouter();
  const [mfa, setMfa] = useState<MfaStatus | null>(null);
  const [passwordCode, setPasswordCode] = useState("");
  const [proofCode, setProofCode] = useState("");
  const [password, setPassword] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [proof, setProof] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function load() {
    setMfa(await api<MfaStatus>("/auth/mfa/status"));
  }
  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await run();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Não foi possível concluir.",
      );
    } finally {
      setBusy(false);
    }
  }
  function changePassword(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    action(async () => {
      await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({
          current_password: password,
          new_password: next,
          code: passwordCode,
        }),
      });
      setPasswordCode("");
      setPassword("");
      setNext("");
      setConfirm("");
      router.replace("/login");
    });
  }

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES"
        title="Minha segurança"
        description="Gerencie sua senha e os acessos à sua conta."
      />
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
      <MfaSettings onStatusChange={setMfa} />
      <div className="security-grid">
        <section className="security-card">
          <h2>Alterar senha</h2>
          <p>
            Ao salvar, todas as suas sessões serão encerradas. Entre novamente
            com a nova senha.
          </p>
          <form onSubmit={changePassword}>
            <label>
              Senha atual
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>
            <label>
              Nova senha
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                value={next}
                onChange={(event) => setNext(event.target.value)}
                required
              />
            </label>
            <label>
              Confirmar nova senha
              <input
                type="password"
                autoComplete="new-password"
                minLength={12}
                maxLength={128}
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </label>
            <label>
              Código MFA ou de recuperação{!mfa?.enabled && " (se ativado)"}
              <input
                autoComplete="one-time-code"
                maxLength={64}
                value={passwordCode}
                onChange={(e) => setPasswordCode(e.target.value)}
                required={mfa?.enabled}
              />
            </label>
            <button className="button primary" disabled={busy}>
              Salvar senha
            </button>
          </form>
        </section>
        <section className="security-card">
          <h2>Confirmar identidade</h2>
          <p>
            Confirme sua senha e o segundo fator, quando ativado, para autorizar
            ações administrativas sensíveis pelos próximos cinco minutos.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              action(async () => {
                await api("/auth/reauthenticate", {
                  method: "POST",
                  body: JSON.stringify({ password: proof, code: proofCode }),
                });
                setProofCode("");
                setProof("");
                setMessage("Identidade confirmada por cinco minutos.");
              });
            }}
          >
            <label>
              Sua senha
              <input
                type="password"
                autoComplete="current-password"
                value={proof}
                onChange={(event) => setProof(event.target.value)}
                required
              />
            </label>
            <label>
              Código MFA ou de recuperação{!mfa?.enabled && " (se ativado)"}
              <input
                autoComplete="one-time-code"
                maxLength={64}
                value={proofCode}
                onChange={(e) => setProofCode(e.target.value)}
                required={mfa?.enabled}
              />
            </label>
            <button className="button" disabled={busy}>
              Confirmar identidade
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
