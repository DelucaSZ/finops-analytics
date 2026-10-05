"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Check, Play, X } from "lucide-react";
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
      return "Já existe uma coleta em andamento para esta conta ou a coleta manual está temporariamente indisponível.";
    }
    if (error.status === 403) {
      return "Você não tem permissão para iniciar esta coleta.";
    }
    if (error.status === 422) {
      return "A conta não atende mais às condições necessárias para iniciar a coleta.";
    }
    return error.message;
  }
  return error instanceof Error
    ? error.message
    : "Não foi possível solicitar a coleta. Tente novamente.";
}

export function ManualCollectionLauncher() {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const openerRef = useRef<HTMLButtonElement>(null);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
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
        setLoadError("Não foi possível carregar as contas disponíveis para coleta manual.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
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
    dialogRef.current?.showModal();
  }

  function closeDialog() {
    if (submitting) return;
    dialogRef.current?.close();
    setError("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting || !cloudAccountId) return;
    const selected = eligibleAccounts.find(
      (account) => String(account.id) === cloudAccountId,
    );
    if (!selected) {
      setError("Selecione uma conta elegível para coleta manual.");
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
      setMessage(`Coleta de ${selected.name} solicitada com sucesso.`);
      dialogRef.current?.close();
      window.setTimeout(() => setMessage(""), 5000);
    } catch (requestError) {
      setError(manualCollectionError(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !canAnalyze) return null;

  return (
    <>
      <div className={`${styles.launcher} header-actions`}>
        <button
          ref={openerRef}
          type="button"
          className="button primary"
          onClick={openDialog}
        >
          <Play size={16} aria-hidden="true" /> Executar coleta
        </button>
      </div>

      <div aria-live="polite">
        {message && (
          <div className={`alert success ${styles.feedback}`}>
            <Check size={17} aria-hidden="true" /> {message}
          </div>
        )}
      </div>

      <dialog
        ref={dialogRef}
        aria-labelledby="manual-collection-title"
        aria-describedby="manual-collection-description"
        onClose={() => openerRef.current?.focus()}
        onCancel={(event) => {
          if (submitting) event.preventDefault();
        }}
        className={`panel ${styles.dialog}`}
      >
        <form method="dialog" onSubmit={submit}>
          <div className="panel-heading">
            <div>
              <span className="eyebrow">COLETA MANUAL</span>
              <h2 id="manual-collection-title">Executar coleta</h2>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label="Fechar"
              onClick={closeDialog}
              disabled={submitting}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>

          <div className={styles.body}>
            <p id="manual-collection-description" className={styles.description}>
              Selecione uma cloud e uma conta conectada. O escopo já configurado na conta será utilizado.
            </p>

            {loadError ? (
              <div className={`alert error ${styles.inlineAlert}`} role="alert">
                {loadError}
              </div>
            ) : eligibleProviders.length === 0 ? (
              <div role="status">
                <p>Nenhuma conta disponível para coleta manual.</p>
                <Link href="/settings/accounts" className="button ghost" onClick={closeDialog}>
                  Ir para Contas
                </Link>
              </div>
            ) : (
              <>
                <label className={styles.field}>
                  Cloud
                  <select
                    aria-label="Cloud"
                    value={provider}
                    onChange={(event) => {
                      setProvider(event.target.value);
                      setCloudAccountId("");
                      setError("");
                    }}
                    disabled={submitting}
                    autoFocus
                  >
                    <option value="">Selecione</option>
                    {eligibleProviders.map((item) => (
                      <option key={item.provider} value={item.provider}>
                        {item.label || providerLabel(item.provider)}
                      </option>
                    ))}
                  </select>
                </label>

                <label className={styles.field}>
                  Conta
                  <select
                    aria-label="Conta"
                    value={cloudAccountId}
                    onChange={(event) => {
                      setCloudAccountId(event.target.value);
                      setError("");
                    }}
                    disabled={submitting || !provider}
                  >
                    <option value="">Selecione</option>
                    {providerAccounts.map((account) => (
                      <option key={account.id} value={String(account.id)}>
                        {account.name}
                      </option>
                    ))}
                  </select>
                </label>

                {provider && providerAccounts.length === 0 && (
                  <p role="status">Nenhuma conta elegível para esta cloud.</p>
                )}
              </>
            )}

            {error && (
              <div className={`alert error ${styles.inlineAlert}`} role="alert">
                {error}
              </div>
            )}

            <div className={styles.actions}>
              <button
                type="button"
                className="button ghost"
                onClick={closeDialog}
                disabled={submitting}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="button primary"
                disabled={submitting || !cloudAccountId || eligibleProviders.length === 0}
              >
                {submitting ? "Solicitando…" : "Executar coleta"}
              </button>
            </div>
          </div>
        </form>
      </dialog>
    </>
  );
}
