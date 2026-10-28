"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Play } from "lucide-react";
import {
  Alert,
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Select,
  useToast,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
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
      return "Já existe uma execução em andamento para esta conta ou o processamento manual está temporariamente indisponível.";
    }
    if (error.status === 403) {
      return "Você não tem permissão para iniciar esta execução.";
    }
    if (error.status === 422) {
      return "A conta não atende mais às condições necessárias para iniciar o processamento.";
    }
    return error.message;
  }
  return error instanceof Error
    ? error.message
    : "Não foi possível solicitar o processamento. Tente novamente.";
}

export function ManualCollectionLauncher() {
  const { toast } = useToast();
  const [open, setOpen] = useState(false);
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [provider, setProvider] = useState("");
  const [cloudAccountId, setCloudAccountId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

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
        setLoadError("Não foi possível carregar as contas disponíveis para processamento manual.");
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (submitting || !cloudAccountId) return;
    const selected = eligibleAccounts.find(
      (account) => String(account.id) === cloudAccountId,
    );
    if (!selected) {
      setError("Selecione uma conta elegível para processamento manual.");
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
      setOpen(false);
      toast({
        variant: "success",
        title: "Relatório enviado para processamento",
        description: `A execução de ${selected.name} foi solicitada e aparecerá no histórico conforme o processamento avançar.`,
      });
    } catch (requestError) {
      setError(manualCollectionError(requestError));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading || !canAnalyze) return null;

  const providerOptions = eligibleProviders.map((item) => ({
    value: item.provider,
    label: item.label || providerLabel(item.provider),
  }));
  const accountOptions = providerAccounts.map((account) => ({
    value: String(account.id),
    label: account.name,
  }));

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (submitting) return;
        setError("");
        if (nextOpen && eligibleProviders.length === 1) {
          setProvider(eligibleProviders[0].provider);
        }
        setOpen(nextOpen);
      }}
    >
      <DialogTrigger leadingIcon={<Play {...iconDefaults} />}>
        Gerar relatório
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>Gerar relatório</DialogTitle>
            <DialogDescription>
              Selecione uma cloud e uma conta conectada. O escopo configurado na conta será usado para iniciar uma nova execução assíncrona.
            </DialogDescription>
          </DialogHeader>

          {loadError ? (
            <Alert variant="danger" title="Contas indisponíveis" description={loadError} />
          ) : eligibleProviders.length === 0 ? (
            <Alert
              variant="info"
              title="Nenhuma conta disponível"
              description="Não há conta elegível para processamento manual neste momento."
              actions={<Link href="/settings/accounts">Ir para Contas</Link>}
            />
          ) : (
            <>
              <Select
                label="Cloud"
                placeholder="Selecione uma cloud"
                value={provider}
                options={providerOptions}
                disabled={submitting}
                onChange={(event) => {
                  setProvider(event.target.value);
                  setCloudAccountId("");
                  setError("");
                }}
              />
              <Select
                label="Conta"
                placeholder={provider ? "Selecione uma conta" : "Selecione uma cloud primeiro"}
                value={cloudAccountId}
                options={accountOptions}
                disabled={submitting || !provider || accountOptions.length === 0}
                helperText={provider && accountOptions.length === 0 ? "Nenhuma conta elegível para esta cloud." : undefined}
                onChange={(event) => {
                  setCloudAccountId(event.target.value);
                  setError("");
                }}
              />
            </>
          )}

          {error ? <Alert variant="danger" title="Não foi possível iniciar o processamento" description={error} /> : null}

          <DialogFooter>
            <DialogClose disabled={submitting}>Cancelar</DialogClose>
            <Button
              type="submit"
              loading={submitting}
              disabled={!cloudAccountId || eligibleProviders.length === 0}
            >
              Enviar para processamento
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
