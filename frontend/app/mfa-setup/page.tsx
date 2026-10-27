"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthLayout } from "@/components/auth/auth-layout";
import { MfaSettings } from "@/components/mfa-settings";
import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api";
import { PRODUCT_NAME } from "@/lib/brand";
import styles from "./mfa-setup.module.css";

export default function MfaSetupPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);

  async function logout() {
    setError("");
    setLeaving(true);
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível sair.");
    } finally {
      setLeaving(false);
    }
  }

  return (
    <AuthLayout>
      <div className={styles.heading}>
        <h1 className={styles.title}>Proteja sua conta {PRODUCT_NAME}</h1>
        <p className={styles.description}>
          Conclua a configuração do segundo fator antes de acessar a plataforma.
        </p>
      </div>
      <MfaSettings enrollment />
      {error && <Alert variant="danger" description={error} />}
      <Button
        className={styles.logout}
        variant="outline"
        loading={leaving}
        onClick={() => void logout()}
      >
        Sair
      </Button>
    </AuthLayout>
  );
}
