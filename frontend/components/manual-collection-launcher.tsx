"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Play } from "lucide-react";
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
} from "@/components/ui";
import { iconDefaults } from "@/lib/iconography";
import styles from "@/components/manual-collection-launcher.module.css";
import { ApiError, api } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import {
  accountsForManualCollectionProvider,
  eligibleManualCollectionAccounts,
  eligibleManualCollectionProviders,
} from "@/lib/manual-collection.mjs";
import { queryKeys } from "@/lib/query-keys.mjs";
import { invalidateApiQueries } from "@/lib/server-state";
import { canRunCloudAnalysis } from "@/lib/settings-navigation.mjs";
import type { CloudAccount, ProviderCapabilities, Scan } from "@/lib/types";

type CurrentUser = { role: string };

function manualCollectionError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return "MANUAL_CONFLICT";
    }
    if (error.status === 403) {
      return "MANUAL_FORBIDDEN";
    }
    if (error.status === 422) {
      return "MANUAL_INELIGIBLE";
    }
    return error.message;
  }
  return error instanceof Error
    ? error.message
    : "MANUAL_REQUEST_FAILED";
}

export function ManualCollectionLauncher() {
  const t = useTranslations("collections.manual");
  const messageTimer = useRef<number | null>(null);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState("");
  const [cloudAccountId, setCloudAccountId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const canAnalyze = canRunCloudAnalysis(role);
  const eligibleAccounts = useMemo(
    () => eligibleManualCollectionAccounts(accounts, capabilities),
    [accounts, capabilities],
  );
  const eligibleProviders = useMemo(
    () => eligibleManualCollectionProviders(accounts, capabilities),
    [accounts, capabilities],
  );
  const providerAccounts = useMemo(
    () => accountsForManualCollectionProvider(accounts, capabilities, provider),
    [accounts, capabilities, provider],
  );

  useEffect(() => {
    let active = true;
    Promise.all([
      api<CloudAccount[]>("/cloud-accounts"),
      api<ProviderCapabilities[]>("/cloud-accounts/capabilities"),
      api<CurrentUser>("/auth/me"),
    ])
      .then(([accountItems, providerCapabilities, user]) => {
        if (!active) return;
        setAccounts(accountItems);
        setCapabilities(providerCapabilities);
        setRole(user.role);
        setLoadError("");
      })
      .catch(() => {
        if (!active) return;
        setLoadError("MANUAL_LOAD_FAILED");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      if (messageTimer.current !== null) window.clearTimeout(messageTimer.current);
    };
  }, []);

  useEffect(() => {
    if (!provider && eligibleProviders.length === 1) {
      setProvider(eligibleProviders[0].provider);
    }
  }, [eligibleProviders, provider]);

  useEffect(() => {
    if (!provider) {
      setCloudAccountId("");
      return;
    }
    if (
      cloudAccountId &&
      !providerAccounts.some((account) => String(account.id) === cloudAccountId)
    ) {
      setCloudAccountId("");
      return;
    }
    if (!cloudAccountId && providerAccounts.length === 1) {
      setCloudAccountId(String(providerAccounts[0].id));
    }
  }, [cloudAccountId, provider, providerAccounts]);

  function openDialog() {
    setError("");
    setMessage("");
    if (eligibleProviders.length === 1) {
      setProvider(eligibleProviders[0].provider);
    }
    setOpen(true);
  }

  function closeDialog() {
    if (submitting) return;
    setOpen(false);
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting || !cloudAccountId) return;
    const selected = eligibleAccounts.find(
      (account) => String(account.id) === cloudAccountId,
    );
    if (!selected) {
      setError("MANUAL_SELECT_ACCOUNT");
      return;
    }

    setSubmitting(true);
    setError("");
    try {
      await api<Scan>(`/cloud-accounts/${selected.id}/scans`, {
        method: "POST",
      });
      invalidateApiQueries(queryKeys.dashboard.all);
      invalidateApiQueries(queryKeys.collections.all);
      setMessage(selected.name);
      setOpen(false);
      if (messageTimer.current !== null) window.clearTimeout(messageTimer.current);
      messageTimer.current = window.setTimeout(() => setMessage(""), 5000);
    } catch (requestError) {
      setError(manualCollectionError(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !canAnalyze) return null;

  return (
    <>
      <div className={styles.launcher}>
        <Button leadingIcon={<Play {...iconDefaults} />} onClick={openDialog}>
          Executar coleta
        </Button>
      </div>

      {message && <Alert className={styles.feedback} variant="success" description={t("success", {account: message})} />}

      <Dialog
        open={open}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) closeDialog();
          else setOpen(true);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("execute")}</DialogTitle>
            <DialogDescription>
              {t("description")}
            </DialogDescription>
          </DialogHeader>

          <form className={styles.form} onSubmit={submit}>
            {loadError ? (
              <Alert variant="danger" description={loadError === "MANUAL_LOAD_FAILED" ? t("loadFailed") : loadError} />
            ) : eligibleProviders.length === 0 ? (
              <Alert
                variant="info"
                title={t("noAccount")}
                actions={(
                  <Link href="/settings/accounts" className={styles.linkAction} onClick={closeDialog}>
                    {t("goToAccounts")}
                  </Link>
                )}
              />
            ) : (
              <>
                <Select
                  label={t("provider")}
                  value={provider}
                  placeholder={t("select")}
                  disabled={submitting}
                  options={eligibleProviders.map((item) => ({
                    value: item.provider,
                    label: item.label || providerLabel(item.provider),
                  }))}
                  onChange={(event) => {
                    setProvider(event.target.value);
                    setCloudAccountId("");
                    setError("");
                  }}
                />
                <Select
                  label={t("account")}
                  value={cloudAccountId}
                  placeholder={t("select")}
                  disabled={submitting || !provider}
                  helperText={provider && providerAccounts.length === 0 ? t("noProviderAccounts") : undefined}
                  options={providerAccounts.map((account) => ({
                    value: String(account.id),
                    label: account.name,
                  }))}
                  onChange={(event) => {
                    setCloudAccountId(event.target.value);
                    setError("");
                  }}
                />
              </>
            )}

            {error && <Alert variant="danger" description={error === "MANUAL_CONFLICT" ? t("errors.conflict") : error === "MANUAL_FORBIDDEN" ? t("errors.forbidden") : error === "MANUAL_INELIGIBLE" ? t("errors.ineligible") : error === "MANUAL_REQUEST_FAILED" ? t("errors.failed") : error === "MANUAL_SELECT_ACCOUNT" ? t("errors.selectAccount") : error} />}

            <DialogFooter className={styles.actions}>
              <Button variant="secondary" onClick={closeDialog} disabled={submitting}>
                Cancelar
              </Button>
              <Button
                type="submit"
                loading={submitting}
                disabled={!cloudAccountId || eligibleProviders.length === 0}
              >
                Executar coleta
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
