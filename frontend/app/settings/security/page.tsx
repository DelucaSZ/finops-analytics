"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { PageHeader, Section } from "@/components/aven";
import { Alert, Button, Input } from "@/components/ui";
import { MfaSettings, MfaStatus } from "@/components/mfa-settings";
import { api } from "@/lib/api";
import styles from "../settings-page.module.css";

export default function SecurityPage() {
  const t = useTranslations("settings.security");
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
    load().catch((err) => setError(err instanceof Error ? err.message : "ERR_SECURITY_LOAD"));
  }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await run();
    } catch (err) {
      setError(err instanceof Error ? err.message : "ERR_SECURITY_ACTION");
    } finally {
      setBusy(false);
    }
  }

  function changePassword(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) {
      setError("ERR_PASSWORD_MISMATCH");
      return;
    }
    void action(async () => {
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
        title={t("title")}
        description={t("description")}
      />

      {error && <Alert variant="danger" title={t("actionFailed")} description={error === "ERR_SECURITY_LOAD" ? t("loadFailed") : error === "ERR_SECURITY_ACTION" ? t("actionFailed") : error === "ERR_PASSWORD_MISMATCH" ? t("passwordMismatch") : error} />}
      {message && <Alert variant="success" title={t("actionDone")} description={message === "IDENTITY_CONFIRMED" ? t("identityConfirmed") : message} />}

      <MfaSettings onStatusChange={setMfa} />

      <div className={styles.sectionGrid}>
        <Section
          appearance="card"
          title={t("changePassword")}
          description={t("changePasswordDescription")}
        >
          <form onSubmit={changePassword} className={styles.formStack}>
            <Input
              label={t("currentPassword")}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <Input
              label={t("newPassword")}
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
            <Input
              label={t("confirmPassword")}
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
            <Input
              label={t("mfaCode", {suffix: !mfa?.enabled ? t("ifEnabled") : ""})}
              autoComplete="one-time-code"
              maxLength={64}
              value={passwordCode}
              onChange={(event) => setPasswordCode(event.target.value)}
              required={mfa?.enabled}
            />
            <div className={styles.formActions}>
              <Button type="submit" loading={busy}>{t("savePassword")}</Button>
            </div>
          </form>
        </Section>

        <Section
          appearance="card"
          title={t("confirmIdentity")}
          description={t("confirmIdentityDescription")}
        >
          <form
            className={styles.formStack}
            onSubmit={(event) => {
              event.preventDefault();
              void action(async () => {
                await api("/auth/reauthenticate", {
                  method: "POST",
                  body: JSON.stringify({ password: proof, code: proofCode }),
                });
                setProofCode("");
                setProof("");
                setMessage("IDENTITY_CONFIRMED");
              });
            }}
          >
            <Input
              label={t("yourPassword")}
              type="password"
              autoComplete="current-password"
              value={proof}
              onChange={(event) => setProof(event.target.value)}
              required
            />
            <Input
              label={t("mfaCode", {suffix: !mfa?.enabled ? t("ifEnabled") : ""})}
              autoComplete="one-time-code"
              maxLength={64}
              value={proofCode}
              onChange={(event) => setProofCode(event.target.value)}
              required={mfa?.enabled}
            />
            <div className={styles.formActions}>
              <Button type="submit" variant="outline" loading={busy}>{t("confirmIdentity")}</Button>
            </div>
          </form>
        </Section>
      </div>
    </>
  );
}
