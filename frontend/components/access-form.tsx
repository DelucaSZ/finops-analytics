"use client";

import Link from "next/link";
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
import { iconDefaults } from "@/lib/iconography";
import styles from "./access-form.module.css";

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
    window.history.replaceState(null, "", window.location.pathname);
    if (value.length !== 43) {
      setError("Link inválido. Abra o link completo recebido ou solicite um novo.");
    }
    setReady(true);
  }, [mode]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (mode !== "forgot" && password !== confirm) {
      setError("As senhas não conferem.");
      return;
    }
    setLoading(true);
    try {
      const path = mode === "forgot"
        ? "/auth/forgot-password"
        : mode === "invite"
          ? "/auth/accept-invitation"
          : "/auth/reset-password";
      const result = await api<{ message: string }>(path, {
        method: "POST",
        body: JSON.stringify(mode === "forgot" ? { email } : { token, password }),
      });
      setMessage(result.message);
      setPassword("");
      setConfirm("");
      setToken("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível concluir.");
    } finally {
      setLoading(false);
    }
  }

  const title = mode === "forgot"
    ? "Recuperar acesso"
    : mode === "invite"
      ? "Ativar sua conta"
      : "Definir nova senha";
  const description = mode === "forgot"
    ? "Informe o e-mail da sua conta para solicitar a recuperação."
    : "Escolha uma senha de 12 a 128 caracteres. Após concluir, entre pela página de login.";
  const submitLabel = mode === "forgot" ? "Solicitar recuperação" : "Salvar senha";
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
            <Alert variant="success" description={message} />
          ) : (
            <form className={styles.form} onSubmit={submit}>
              {mode === "forgot" ? (
                <Input
                  type="email"
                  label="E-mail"
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
                    label="Nova senha"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                  <Input
                    type="password"
                    label="Confirmar senha"
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

          {error && <Alert variant="danger" description={error} />}
        </CardContent>

        <CardFooter className={styles.footer}>
          <Link className={styles.link} href="/login">
            Voltar para o login
          </Link>
        </CardFooter>
      </Card>
    </AuthLayout>
  );
}
