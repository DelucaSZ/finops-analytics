"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { FormEvent, useEffect, useRef, useState } from "react";
import { LockKeyhole } from "lucide-react";
import { AuthLayout } from "@/components/auth/auth-layout";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  Input,
} from "@/components/ui";
import { api } from "@/lib/api";
import { authErrorKey, type AuthErrorKey } from "@/lib/auth-error";
import { iconDefaults } from "@/lib/iconography";
import styles from "./access-form.module.css";

export function AccessForm({ mode }: { mode: "forgot" | "reset" | "invite" }) {
  const t = useTranslations("auth");
  const initialized = useRef("");
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<AuthErrorKey | "passwordMismatch" | "invalidLink" | null>(null);
  const [message, setMessage] = useState(false);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(mode === "forgot");

  useEffect(() => {
    if (mode === "forgot" || initialized.current === mode) return;
    initialized.current = mode;
    const value = new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    setToken(value);
    window.history.replaceState(null, "", window.location.pathname);
    if (value.length !== 43) {
      setError("invalidLink");
    }
    setReady(true);
  }, [mode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (mode !== "forgot" && password !== confirm) {
      setError("passwordMismatch");
      return;
    }
    setLoading(true);
    try {
      const path = mode === "forgot"
        ? "/auth/forgot-password"
        : mode === "invite"
          ? "/auth/accept-invitation"
          : "/auth/reset-password";
      await api<{ message: string }>(path, {
        method: "POST",
        body: JSON.stringify(mode === "forgot" ? { email } : { token, password }),
      });
      setMessage(true);
      setPassword("");
      setConfirm("");
      setToken("");
    } catch (err) {
      setError(authErrorKey(err, "access"));
    } finally {
      setLoading(false);
    }
  }

  const title = t(`access.${mode}.title`);
  const description = mode === "forgot"
    ? t("access.forgot.description")
    : t("access.passwordInstructions", { min: 12, max: 128 });
  const submitLabel = t(`access.${mode}.submit`);
  const submitDisabled = !ready || (mode !== "forgot" && token.length !== 43);

  return (
    <AuthLayout>
      <Card className={styles.card}>
        <CardHeader className={styles.header}>
          <span className={styles.icon} aria-hidden="true">
            <LockKeyhole {...iconDefaults} />
          </span>
          <h1 className={styles.title}>{title}</h1>
          <p className={styles.description}>{description}</p>
        </CardHeader>

        <CardContent className={styles.content}>
          {message ? (
            <Alert variant="success" description={t(`access.${mode}.success`)} />
          ) : (
            <form className={styles.form} onSubmit={submit}>
              {mode === "forgot" ? (
                <Input
                  type="email"
                  label={t("access.email")}
                  autoComplete="email"
                  maxLength={254}
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
              ) : (
                <>
                  <Input
                    type="password"
                    label={t("access.newPassword")}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <Input
                    type="password"
                    label={t("access.confirmPassword")}
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={confirm}
                    onChange={(event) => setConfirm(event.target.value)}
                    required
                  />
                </>
              )}
              <Button
                className={styles.submit}
                type="submit"
                loading={loading}
                disabled={submitDisabled}
              >
                {submitLabel}
              </Button>
            </form>
          )}

          {error && <Alert variant="danger" description={error === "passwordMismatch" ? t("access.passwordMismatch") : error === "invalidLink" ? t("access.invalidLink") : t(`errors.${error}`)} />}
        </CardContent>

        <CardFooter className={styles.footer}>
          <Link className={styles.link} href="/login">
            {t("access.backToLogin")}
          </Link>
        </CardFooter>
      </Card>
    </AuthLayout>
  );
}
