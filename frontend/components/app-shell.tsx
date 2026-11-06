"use client";

import { useRouter, usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useEffect, useState, type ReactNode } from "react";
import { ApplicationShell, type ShellUser } from "@/components/app-shell/application-shell";
import { Button, Spinner } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { clearApiQueryCache } from "@/lib/server-state";
import styles from "@/components/app-shell/app-shell.module.css";

const publicRoutes = [
  "/mfa-setup",
  "/login",
  "/forgot-password",
  "/reset-password",
  "/accept-invitation",
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const tSession = useTranslations("shell.session");
  const tCommon = useTranslations("common.actions");
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<ShellUser | null>(null);
  const [error, setError] = useState("");
  const [leaving, setLeaving] = useState(false);
  const [retry, setRetry] = useState(0);
  const isPublic = publicRoutes.includes(pathname);

  useEffect(() => {
    const clearPrivateCache = () => clearApiQueryCache();
    window.addEventListener("deepops:session-invalidated", clearPrivateCache);
    return () => window.removeEventListener("deepops:session-invalidated", clearPrivateCache);
  }, []);

  useEffect(() => {
    let active = true;
    window.localStorage.removeItem("nuvemiq_token");
    setReady(false);
    setError("");

    if (isPublic) {
      clearApiQueryCache();
      setSession(null);
      setReady(true);
      return;
    }

    api<ShellUser>("/auth/me", {}, false)
      .then((user) => {
        if (!active) return;
        setSession(user);
        setReady(true);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          clearApiQueryCache();
          router.replace("/login");
        } else {
          setError("SESSION_VERIFICATION_FAILED");
        }
      });

    return () => {
      active = false;
    };
  }, [isPublic, router, retry]);

  async function logout() {
    setLeaving(true);
    setError("");
    try {
      await api("/auth/logout", { method: "POST" });
      clearApiQueryCache();
      router.replace("/login");
    } catch (err) {
      setError(err instanceof Error ? err.message : "SIGN_OUT_FAILED");
    } finally {
      setLeaving(false);
    }
  }

  const displayError = error === "SESSION_VERIFICATION_FAILED"
    ? tSession("verificationFailed")
    : error === "SIGN_OUT_FAILED" ? tSession("signOutFailed") : error;

  if (error && !ready) {
    return (
      <main className={styles.bootScreen}>
        <p role="alert">{displayError}</p>
        <Button onClick={() => setRetry((value) => value + 1)}>{tCommon("retry")}</Button>
      </main>
    );
  }

  if (!ready) {
    return (
      <main className={styles.bootScreen} aria-live="polite">
        <Spinner label={tSession("checkingAccess")} />
        <span>{tSession("checkingAccessProgress")}</span>
      </main>
    );
  }

  if (isPublic) return <>{children}</>;

  return (
    <ApplicationShell
      user={session}
      leaving={leaving}
      statusMessage={displayError}
      onLogout={logout}
    >
      {children}
    </ApplicationShell>
  );
}
