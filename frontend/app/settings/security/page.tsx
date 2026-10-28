"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader, Section } from "@/components/aven";
import { Alert, Button, Input } from "@/components/ui";
import { MfaSettings, MfaStatus } from "@/components/mfa-settings";
import { api } from "@/lib/api";
import styles from "../settings-layout.module.css";

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
    load().catch((err) => setError(err instanceof Error ? err.message : "Não foi possível carregar a segurança da conta."));
  }, []);

  async function action(run: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await run();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível concluir.");
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
        title="Minha segurança"
        description="Gerencie sua senha, autenticação multifator e autorização de ações sensíveis."
      />

      {error && <Alert variant="danger" title="Não foi possível concluir" description={error} />}
      {message && <Alert variant="success" title="Alteração concluída" description={message} />}

      <MfaSettings onStatusChange={setMfa} />

      <div className={styles.sectionGrid}>
        <Section
          appearance="card"
          title="Alterar senha"
          description="Ao salvar, todas as suas sessões serão encerradas. Entre novamente com a nova senha."
        >
          <form onSubmit={changePassword} className={styles.formStack}>
            <Input
              label="Senha atual"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <Input
              label="Nova senha"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={next}
              onChange={(event) => setNext(event.target.value)}
              required
            />
            <Input
              label="Confirmar nova senha"
              type="password"
              autoComplete="new-password"
              minLength={12}
              maxLength={128}
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              required
            />
            <Input
              label={`Código MFA ou de recuperação${!mfa?.enabled ? " (se ativado)" : ""}`}
              autoComplete="one-time-code"
              maxLength={64}
              value={passwordCode}
              onChange={(event) => setPasswordCode(event.target.value)}
              required={mfa?.enabled}
            />
            <div className={styles.formActions}>
              <Button type="submit" loading={busy}>Salvar senha</Button>
            </div>
          </form>
        </Section>

        <Section
          appearance="card"
          title="Confirmar identidade"
          description="Confirme sua senha e o segundo fator, quando ativado, para autorizar ações administrativas sensíveis pelos próximos cinco minutos."
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
                setMessage("Identidade confirmada por cinco minutos.");
              });
            }}
          >
            <Input
              label="Sua senha"
              type="password"
              autoComplete="current-password"
              value={proof}
              onChange={(event) => setProof(event.target.value)}
              required
            />
            <Input
              label={`Código MFA ou de recuperação${!mfa?.enabled ? " (se ativado)" : ""}`}
              autoComplete="one-time-code"
              maxLength={64}
              value={proofCode}
              onChange={(event) => setProofCode(event.target.value)}
              required={mfa?.enabled}
            />
            <div className={styles.formActions}>
              <Button type="submit" variant="outline" loading={busy}>Confirmar identidade</Button>
            </div>
          </form>
        </Section>
      </div>
    </>
  );
}
