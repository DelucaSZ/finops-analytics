"use client";
import { useState } from "react";
import { api } from "@/lib/api";

export function IdentityProof() {
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  return (
    <section className="security-card" id="identity-proof" tabIndex={-1}>
      <h2>Confirmar identidade</h2>
      <p>
        Se solicitado, confirme sua senha e seu código MFA (quando ativado). A
        confirmação autoriza alterações por cinco minutos.
      </p>
      <form
        className="settings-inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          setMessage("");
          try {
            await api("/auth/reauthenticate", {
              method: "POST",
              body: JSON.stringify({ password, code }),
            });
            setPassword("");
            setCode("");
            setMessage("Identidade confirmada. Repita a ação desejada.");
          } catch (err) {
            setError(
              err instanceof Error
                ? err.message
                : "Não foi possível confirmar.",
            );
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          Senha
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <label>
          Código MFA ou de recuperação
          <input
            autoComplete="one-time-code"
            maxLength={64}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <button className="button" disabled={busy}>
          Confirmar identidade
        </button>
      </form>
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
    </section>
  );
}
