"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
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
  const [status, setStatus] = useState<MfaStatus | null>(null);
  const [setup, setSetup] = useState<Setup | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [confirmCode, setConfirmCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
        setError(err instanceof Error ? err.message : "Não foi possível carregar a configuração.");
      });
    return () => {
      active = false;
    };
  }, [onStatusChange]);

  async function run(action: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível concluir.");
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
        <CardTitle>Autenticação em duas etapas</CardTitle>
        <CardDescription>
          Use Google Authenticator, Microsoft Authenticator ou outro aplicativo compatível com TOTP.
        </CardDescription>
      </CardHeader>

      <CardContent className={styles.content}>
        {error && <Alert variant="danger" description={error} />}

        {!status && <Spinner label="Carregando configuração de MFA" />}

        {status && (
          <Alert
            variant={status.enabled ? "success" : "info"}
            title={status.enabled ? "MFA ativado" : "MFA ainda não ativado"}
            description={
              status.enabled
                ? `${status.recovery_codes_remaining} códigos de recuperação disponíveis.`
                : undefined
            }
          />
        )}

        {status?.enrollment_required && (
          <p className={styles.statusCopy}>Cadastre seu autenticador para acessar a plataforma.</p>
        )}

        {enrollment && status?.enabled && !setup && codes.length === 0 && (
          <Button onClick={() => router.replace("/")}>Acessar plataforma</Button>
        )}

        {codes.length > 0 ? (
          <div className={styles.stack}>
            <h3 className={styles.sectionTitle}>Guarde seus códigos de recuperação</h3>
            <p className={styles.helper}>
              Estes códigos aparecem somente agora. Guarde-os em um gerenciador de senhas. Cada um substitui o código do autenticador uma única vez.
            </p>
            <pre className={styles.recoveryCodes} tabIndex={0}>{codes.join("\n")}</pre>
            <Checkbox
              checked={saved}
              onChange={(event) => setSaved(event.target.checked)}
              label="Guardei os códigos em um local seguro"
            />
            <div className={styles.actions}>
              <Button
                disabled={!saved}
                onClick={() => {
                  setCodes([]);
                  if (enrollment) router.replace("/");
                }}
              >
                Concluir
              </Button>
            </div>
          </div>
        ) : setup ? (
          <form className={styles.form} onSubmit={confirm}>
            <p className={styles.helper}>
              Escaneie o QR code no autenticador ou informe a chave manualmente. A configuração expira em dez minutos.
            </p>
            <span className={styles.qrFrame}>
              {/* Generated by our API; never sent to a QR service or an image optimizer. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                className={styles.qr}
                src={setup.qr_code}
                alt={`QR code para cadastrar seu autenticador ${PRODUCT_NAME}`}
                width={240}
                height={240}
              />
            </span>
            <Input
              label="Chave de configuração"
              readOnly
              value={setup.secret}
              autoComplete="off"
              spellCheck={false}
            />
            <p className={styles.helper}>
              Tipo: baseado em tempo (TOTP) · 6 dígitos · 30 segundos. Não compartilhe a chave.
            </p>
            <Input
              label="Código do novo autenticador"
              autoComplete="one-time-code"
              inputMode="numeric"
              pattern="[0-9]{6}"
              maxLength={6}
              value={confirmCode}
              onChange={(event) => setConfirmCode(event.target.value)}
              required
            />
            <div className={styles.actions}>
              <Button type="submit" loading={busy}>Confirmar ativação</Button>
              <Button
                variant="outline"
                disabled={busy}
                onClick={() => {
                  setSetup(null);
                  setConfirmCode("");
                }}
              >
                Voltar
              </Button>
            </div>
          </form>
        ) : status ? (
          <form className={styles.form} onSubmit={start}>
            {status.enabled && (
              <p className={styles.helper}>
                Para trocar o autenticador ou gerar novos códigos de recuperação, confirme sua senha e um segundo fator. A troca encerra as outras sessões e invalida os códigos anteriores.
              </p>
            )}
            <Input
              type="password"
              label="Sua senha"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            {status.enabled && (
              <Input
                label="Código atual ou de recuperação"
                autoComplete="one-time-code"
                maxLength={64}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                required
              />
            )}
            <div className={styles.actions}>
              <Button type="submit" loading={busy}>
                {status.enabled ? "Trocar autenticador" : "Configurar autenticador"}
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
                  Gerar novos códigos
                </Button>
              )}
            </div>
          </form>
        ) : null}
      </CardContent>
    </Card>
  );
}
