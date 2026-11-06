"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Checkbox,
  Input,
  Spinner,
} from "@/components/ui";
import { api } from "@/lib/api";
import { authErrorKey, type AuthErrorKey } from "@/lib/auth-error";
import { PRODUCT_NAME } from "@/lib/brand";
import styles from "./mfa-settings.module.css";

export type MfaStatus = {
  enabled: boolean;
  enrollment_required: boolean;
  recovery_codes_remaining: number;
};

type Setup = { secret: string; qr_code: string };

export function MfaSettings({
  enrollment = false,
  onStatusChange,
}: {
  enrollment?: boolean;
  onStatusChange?: (status: MfaStatus) => void;
}) {
  const router = useRouter();
  const t = useTranslations("auth.mfa");
  const tErrors = useTranslations("auth.errors");
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [saved, setSaved] = useState(false);

  async function load() {
    const result = await api<MfaStatus>("/auth/mfa/status");
    setStatus(result);
    onStatusChange?.(result);
  }

  useEffect(() => {
    let active = true;
    api<MfaStatus>("/auth/mfa/status")
      .then((result) => {
        if (!active) return;
        setStatus(result);
        onStatusChange?.(result);
      })
      .catch((err) => {
        if (!active) return;
        setError(authErrorKey(err, "configure"));
      });
    return () => {
      active = false;
    };
  }, [onStatusChange]);

  async function run(action: () => Promise<void>) {
    setError(null);
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(authErrorKey(err, "configure"));
    } finally {
      setBusy(false);
    }
  }

  function start(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await api<Setup>("/auth/mfa/setup", {
        method: "POST",
        body: JSON.stringify({ password, code }),
      });
      setSetup(result);
      setPassword("");
      setCode("");
      setCodes([]);
    });
  }

  function confirm(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await api<{ recovery_codes: string[] }>("/auth/mfa/confirm", {
        method: "POST",
        body: JSON.stringify({ code: confirmCode }),
      });
      setSetup(null);
      setConfirmCode("");
      setCodes(result.recovery_codes);
      setSaved(false);
      await load();
    });
  }

  return (
    <Card className={styles.card}>
      <CardHeader>
        <CardTitle>{t("title")}</CardTitle>
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>

      <CardContent className={styles.content}>
        {error && <Alert variant="danger" description={tErrors(error)} />}

        {!status && <Spinner label={t("loading")} />}

        {status && (
          <Alert
            variant={status.enabled ? "success" : "info"}
            title={status.enabled ? t("enabled") : t("notEnabled")}
            description={
              status.enabled
                ? t("recoveryRemaining", { count: status.recovery_codes_remaining })
                : undefined
            }
          />
        )}

        {status?.enrollment_required && (
          <p className={styles.statusCopy}>{t("enrollmentRequired")}</p>
        )}

        {enrollment && status?.enabled && !setup && codes.length === 0 && (
          <Button onClick={() => router.replace("/")}>{t("enterPlatform")}</Button>
        )}

        {codes.length > 0 ? (
          <div className={styles.stack}>
            <h3 className={styles.sectionTitle}>{t("saveCodesTitle")}</h3>
            <p className={styles.helper}>
              {t("saveCodesDescription")}
            </p>
            <pre className={styles.recoveryCodes} tabIndex={0}>{codes.join("\n")}</pre>
            <Checkbox
              checked={saved}
              onChange={(event) => setSaved(event.target.checked)}
              label={t("savedCodes")}
            />
            <div className={styles.actions}>
              <Button
                disabled={!saved}
                onClick={() => {
                  setCodes([]);
                  if (enrollment) router.replace("/");
                }}
              >
                {t("finish")}
              </Button>
            </div>
          </div>
        ) : setup ? (
          <form className={styles.form} onSubmit={confirm}>
            <p className={styles.helper}>
              {t("qrInstructions")}
            </p>
            <span className={styles.qrFrame}>
              {/* Generated by our API; never sent to a QR service or an image optimizer. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className={styles.qr}
                src={setup.qr_code}
                alt={t("qrAlt", { product: PRODUCT_NAME })}
                width={240}
                height={240}
              />
            </span>
            <Input
              label={t("setupSecret")}
              readOnly
              value={setup.secret}
              autoComplete="off"
              spellCheck={false}
            />
            <p className={styles.helper}>
              {t("totpDetails")}
            </p>
            <Input
              label={t("newAuthenticatorCode")}
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={confirmCode}
              onChange={(event) => setConfirmCode(event.target.value)}
              required
            />
            <div className={styles.actions}>
              <Button type="submit" loading={busy}>{t("confirmActivation")}</Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setSetup(null);
                  setConfirmCode("");
                }}
              >
                {t("back")}
              </Button>
            </div>
          </form>
        ) : status ? (
          <form className={styles.form} onSubmit={start}>
            {status.enabled && (
              <p className={styles.helper}>
                {t("replaceWarning")}
              </p>
            )}
            <Input
              type="password"
              label={t("yourPassword")}
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {status.enabled && (
              <Input
                label={t("currentCode")}
                autoComplete="one-time-code"
                maxLength={64}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
              />
            )}
            <div className={styles.actions}>
              <Button type="submit" loading={busy}>
                {status.enabled ? t("replaceAuthenticator") : t("setupAuthenticator")}
              </Button>
              {status.enabled && (
                <Button
                  variant="outline"
                  disabled={busy || !password || !code}
                  onClick={() => void run(async () => {
                    const result = await api<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", {
                      method: "POST",
                      body: JSON.stringify({ password, code }),
                    });
                    setPassword("");
                    setCode("");
                    setCodes(result.recovery_codes);
                    setSaved(false);
                    await load();
                  })}
                >
                  {t("newRecoveryCodes")}
                </Button>
              )}
            </div>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
