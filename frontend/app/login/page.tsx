"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
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
import { authErrorKey, type AuthErrorKey } from "@/lib/auth-error";
import { PRODUCT_NAME } from "@/lib/brand";
import { iconDefaults } from "@/lib/iconography";
import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const t = useTranslations("auth");
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
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
      setError(authErrorKey(err, challenge ? "verify" : "login"));
    } finally {
      setLoading(false);
    }
  }

  const title = challenge ? t("mfa.verifyTitle") : t("login.title");
  const description = challenge
    ? recovery ? t("mfa.recoveryInstruction") : t("mfa.totpInstruction")
    : t("login.description", { product: PRODUCT_NAME });

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
                  label={t("login.email")}
                  autoComplete="username"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  required
                />
                <Input
                  type={showPassword ? "text" : "password"}
                  label={t("login.password")}
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  trailingAction={
                    <IconButton
                      aria-label={showPassword ? t("login.hidePassword") : t("login.showPassword")}
                      tooltip={showPassword ? t("login.hidePassword") : t("login.showPassword")}
                      size="sm"
                      onClick={() => setShowPassword((visible) => !visible)}
                    >
                      {showPassword ? <EyeOff {...iconDefaults} /> : <Eye {...iconDefaults} />}
                    </IconButton>
                  }
                />
                <div className={styles.auxiliary}>
                  <Link className={styles.link} href="/forgot-password">
                    {t("login.forgotPassword")}
                  </Link>
                </div>
              </div>
            ) : (
              <div className={styles.fields}>
                <Input
                  label={recovery ? t("mfa.recoveryCode") : t("mfa.authenticatorCode")}
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
                      setError(null);
                    }}
                  >
                    {recovery ? t("mfa.useAuthenticator") : t("mfa.useRecovery")}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setChallenge("");
                      setCode("");
                      setError(null);
                      setRecovery(false);
                    }}
                  >
                    {t("mfa.backToLogin")}
                  </Button>
                </div>
              </div>
            )}

            {error && <Alert variant="danger" description={t(`errors.${error}`)} />}
          </CardContent>

          <CardFooter className={styles.footer}>
            <Button
              className={styles.submit}
              type="submit"
              variant="primary"
              loading={loading}
              trailingIcon={<ArrowRight {...iconDefaults} />}
            >
              {challenge ? (loading ? t("mfa.verifying") : t("mfa.verify")) : (loading ? t("login.submitting") : t("login.submit"))}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </AuthLayout>
  );
}
