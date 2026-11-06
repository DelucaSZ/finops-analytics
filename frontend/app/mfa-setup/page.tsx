"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useTranslations } from "next-intl";
import { AuthLayout } from "@/components/auth/auth-layout";
import { MfaSettings } from "@/components/mfa-settings";
import { Alert, Button } from "@/components/ui";
import { api } from "@/lib/api";
import { authErrorKey, type AuthErrorKey } from "@/lib/auth-error";
import { PRODUCT_NAME } from "@/lib/brand";
import styles from "./mfa-setup.module.css";

export default function MfaSetupPage() {
  const router = useRouter();
  const t = useTranslations("auth");
  const [error, setError] = useState<AuthErrorKey | null>(null);
  const [leaving, setLeaving] = useState(false);

  async function logout() {
    setError(null);
    setLeaving(true);
    try {
      await api("/auth/logout", { method: "POST" });
      router.replace("/login");
    } catch (err) {
      setError(authErrorKey(err, "logout"));
    } finally {
      setLeaving(false);
    }
  }

  return (
    <AuthLayout>
      <div className={styles.heading}>
        <h1 className={styles.title}>{t("mfa.setupPageTitle", { product: PRODUCT_NAME })}</h1>
        <p className={styles.description}>
          {t("mfa.setupPageDescription")}
        </p>
      </div>
      <MfaSettings enrollment />
      {error && <Alert variant="danger" description={t(`errors.${error}`)} />}
      <Button
        className={styles.logout}
        variant="outline"
        loading={leaving}
        onClick={() => void logout()}
      >
        {leaving ? t("mfa.loggingOut") : t("mfa.logout")}
      </Button>
    </AuthLayout>
  );
}
