"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { ArrowRight, Eye, EyeOff, LockKeyhole } from "lucide-react";
import { AuthLayout } from "@/components/auth/auth-layout";
import {
  Alert,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  IconButton,
  Input,
} from "@/components/ui";
import { api } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import { iconDefaults } from "@/lib/iconography";
import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (challenge) {
        await api("/auth/mfa/verify", {
          method: "POST",
          body: JSON.stringify({ challenge, code }),
        });
        setChallenge("");
        setCode("");
        router.replace("/");
      } else {
        const result = await api<{
          mfa_required?: boolean;
          challenge?: string;
          enrollment_required?: boolean;
        }>("/auth/login", {
          method: "POST",
          body: JSON.stringify({ email, password }),
        });
        setPassword("");
        setShowPassword(false);
        if (result.mfa_required && result.challenge) {
          setChallenge(result.challenge);
        } else {
          router.replace(result.enrollment_required ? "/mfa-setup" : "/");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível entrar");
    } finally {
      setLoading(false);
    }
  }

  const title = challenge ? "Verificar segundo fator" : "Bem-vindo de volta";
  const description = challenge
    ? recovery
      ? "Informe um dos códigos de recuperação que você guardou. Cada código pode ser usado uma vez."
      : "Informe o código de seis dígitos do seu autenticador."
    : `Acesse sua conta ${PRODUCT_NAME} para continuar.`;

  return (
    <AuthLayout>
      <form className={styles.form} onSubmit={submit}>
        <Card className={styles.card}>
          <CardHeader className={styles.header}>
            <span className={styles.loginIcon} aria-hidden="true">
              <LockKeyhole {...iconDefaults} />
            </span>
            <h1 className={styles.title}>{title}</h1>
            <p className={styles.description}>{description}</p>
          </CardHeader>

          <CardContent className={styles.content}>
            {!challenge ? (
              <div className={styles.fields}>
                <Input
                  type="email"
                  label="E-mail"
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
                <Input
                  type={showPassword ? "text" : "password"}
                  label="Senha"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  trailingAction={
                    <IconButton
                      aria-label={showPassword ? "Ocultar senha" : "Mostrar senha"}
                      tooltip={showPassword ? "Ocultar senha" : "Mostrar senha"}
                      size="sm"
                      onClick={() => setShowPassword((visible) => !visible)}
                    >
                      {showPassword ? <EyeOff {...iconDefaults} /> : <Eye {...iconDefaults} />}
                    </IconButton>
                  }
                />
                <div className={styles.auxiliary}>
                  <Link className={styles.link} href="/forgot-password">
                    Esqueci minha senha
                  </Link>
                </div>
              </div>
            ) : (
              <div className={styles.fields}>
                <Input
                  label={recovery ? "Código de recuperação" : "Código do autenticador"}
                  autoComplete="one-time-code"
                  inputMode={recovery ? "text" : "numeric"}
                  pattern={recovery ? undefined : "[0-9]{6}"}
                  maxLength={recovery ? 64 : 6}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  required
                  autoFocus
                />
                <div className={styles.mfaActions}>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setRecovery((current) => !current);
                      setCode("");
                      setError("");
                    }}
                  >
                    {recovery ? "Usar autenticador" : "Usar código de recuperação"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setChallenge("");
                      setCode("");
                      setError("");
                      setRecovery(false);
                    }}
                  >
                    Voltar ao login
                  </Button>
                </div>
              </div>
            )}

            {error && <Alert variant="danger" description={error} />}
          </CardContent>

          <CardFooter className={styles.footer}>
            <Button
              className={styles.submit}
              type="submit"
              variant="primary"
              loading={loading}
              trailingIcon={<ArrowRight {...iconDefaults} />}
            >
              {challenge ? "Verificar" : "Entrar"}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </AuthLayout>
  );
}
