"use client";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { authErrorKey, type AuthErrorKey } from "@/lib/auth-error";
import { api } from "@/lib/api";

export function IdentityProof() {
  const t = useTranslations("auth.identity");
  const tErrors = useTranslations("auth.errors");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [message, setMessage] = useState(false);
  return (
    <section className="security-card" id="identity-proof" tabIndex={-1}>
      <h2>{t("title")}</h2>
      <p>
        {t("description")}
      </p>
      <form
        className="settings-inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          setMessage(false);
          try {
            await api("/auth/reauthenticate", {
              method: "POST",
              body: JSON.stringify({ password, code }),
            });
            setPassword("");
            setCode("");
            setMessage(true);
          } catch (err) {
            setError(authErrorKey(err, "configure"));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          {t("password")}
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        <label>
          {t("code")}
          <input
            autoComplete="one-time-code"
            maxLength={64}
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
        </label>
        <button className="button" disabled={busy}>
          {busy ? t("submitting") : t("submit")}
        </button>
      </form>
      {error && (
        <p className="form-error" role="alert">
          {tErrors(error)}
        </p>
      )}
      {message && (
        <p className="form-success" role="status">
          {t("success")}
        </p>
      )}
    </section>
  );
}
