"use client";

import { useCallback, useEffect, useState } from "react";
import { PageHeader, Section, StatusIndicator } from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Input,
  Select,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  TableState,
} from "@/components/ui";
import {
  BillingGranularity,
  BillingGroupBy,
  BillingMetric,
  BillingProfile,
  BillingProfileInput,
  createBillingProfile,
  deactivateBillingProfile,
  listBillingProfiles,
  setDefaultBillingProfile,
  updateBillingProfile,
} from "@/lib/billing";
import styles from "../../settings-page.module.css";

const RECORD_TYPES = [
  "Credit",
  "DiscountedUsage",
  "Fee",
  "Refund",
  "RIFee",
  "SavingsPlanCoveredUsage",
  "SavingsPlanNegation",
  "SavingsPlanRecurringFee",
  "SavingsPlanUpfrontFee",
  "Tax",
  "Usage",
];

const metricLabels: Record<BillingMetric, string> = {
  AMORTIZED_COST: "Custo amortizado",
  NET_AMORTIZED_COST: "Custo amortizado líquido",
  UNBLENDED_COST: "Custo não combinado",
};
const granularityLabels: Record<BillingGranularity, string> = {
  DAILY: "Diário",
  MONTHLY: "Mensal",
};
const groupingLabels: Record<BillingGroupBy, string> = {
  NONE: "Sem agrupamento",
  SERVICE: "Serviço",
  ACCOUNT: "Conta",
};

type FormState = BillingProfileInput & { id?: string };

const emptyForm: FormState = {
  name: "",
  description: "",
  granularity: "DAILY",
  metric: "AMORTIZED_COST",
  group_by: "NONE",
  exclude_record_types: ["Credit"],
  is_default: false,
};

function message(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function profileSummary(profile: BillingProfile) {
  const exclusions = profile.exclude_record_types.length
    ? `Exclui ${profile.exclude_record_types.join(", ")}`
    : "Sem exclusões";
  return `${granularityLabels[profile.granularity]} · ${metricLabels[profile.metric]} · ${exclusions}`;
}

export default function BillingProfilesPage() {
  const [profiles, setProfiles] = useState<BillingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [form, setForm] = useState<FormState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setProfiles(await listBillingProfiles());
    } catch (err) {
      setError(message(err, "Não foi possível carregar os perfis de Billing."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function edit(profile: BillingProfile) {
    setForm({
      id: profile.id,
      name: profile.name,
      description: profile.description ?? "",
      granularity: profile.granularity,
      metric: profile.metric,
      group_by: profile.group_by,
      exclude_record_types: [...profile.exclude_record_types],
    });
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!form) return;
    setSaving(true);
    setError("");
    setSuccess("");
    const payload: BillingProfileInput = {
      name: form.name.trim(),
      description: form.description?.trim() || null,
      granularity: form.granularity,
      metric: form.metric,
      group_by: form.group_by,
      exclude_record_types: form.exclude_record_types,
      is_default: form.is_default,
    };
    try {
      if (form.id) {
        await updateBillingProfile(form.id, payload);
        setSuccess(`Perfil ${payload.name} atualizado.`);
      } else {
        await createBillingProfile(payload);
        setSuccess(`Perfil ${payload.name} criado.`);
      }
      setForm(null);
      await load();
    } catch (err) {
      setError(message(err, "Não foi possível salvar o perfil."));
    } finally {
      setSaving(false);
    }
  }

  async function setDefault(profile: BillingProfile) {
    setError("");
    setSuccess("");
    try {
      await setDefaultBillingProfile(profile.id);
      setSuccess(`${profile.name} agora é o perfil padrão.`);
      await load();
    } catch (err) {
      setError(message(err, "Não foi possível alterar o perfil padrão."));
    }
  }

  async function deactivate(profile: BillingProfile) {
    setError("");
    setSuccess("");
    try {
      await deactivateBillingProfile(profile.id);
      setSuccess(`${profile.name} foi desativado.`);
      await load();
    } catch (err) {
      setError(message(err, "Não foi possível desativar o perfil."));
    }
  }

  return (
    <>
      <PageHeader
        title="Perfis de Billing"
        description="Salve metodologias reutilizáveis para consultas ao AWS Cost Explorer. Período e contas continuam sendo escolhidos na consulta."
        actions={<Button onClick={() => setForm({ ...emptyForm })}>Novo perfil</Button>}
      />

      {error && <Alert variant="danger" title="Falha em Billing Profiles" description={error} />}
      {success && <Alert variant="success" title="Alteração persistida" description={success} />}

      {form && (
        <Section
          appearance="card"
          title={form.id ? "Editar perfil" : "Novo perfil"}
          description="A configuração é persistida somente após salvar."
        >
          <form onSubmit={submit} className={styles.formStack}>
            <div className={styles.formGrid}>
              <Input
                label="Nome"
                required
                maxLength={120}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
              <Input
                label="Descrição"
                maxLength={1000}
                value={form.description ?? ""}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
              <Select
                label="Métrica"
                value={form.metric}
                onChange={(event) => setForm({ ...form, metric: event.target.value as BillingMetric })}
                options={Object.entries(metricLabels).map(([value, label]) => ({ value, label }))}
              />
              <Select
                label="Granularidade"
                value={form.granularity}
                onChange={(event) => setForm({ ...form, granularity: event.target.value as BillingGranularity })}
                options={Object.entries(granularityLabels).map(([value, label]) => ({ value, label }))}
              />
              <Select
                label="Agrupamento padrão"
                value={form.group_by}
                onChange={(event) => setForm({ ...form, group_by: event.target.value as BillingGroupBy })}
                options={Object.entries(groupingLabels).map(([value, label]) => ({ value, label }))}
              />
              {!form.id && (
                <Checkbox
                  label="Definir como padrão"
                  checked={Boolean(form.is_default)}
                  onChange={(event) => setForm({ ...form, is_default: event.target.checked })}
                />
              )}
            </div>

            <fieldset className={styles.formStack}>
              <legend>Excluir tipos de registro</legend>
              <div className={styles.checkboxGrid}>
                {RECORD_TYPES.map((recordType) => {
                  const checked = form.exclude_record_types.includes(recordType);
                  return (
                    <Checkbox
                      key={recordType}
                      label={recordType}
                      checked={checked}
                      onChange={(event) => {
                        const next = event.target.checked
                          ? [...form.exclude_record_types, recordType]
                          : form.exclude_record_types.filter((item) => item !== recordType);
                        setForm({ ...form, exclude_record_types: next });
                      }}
                    />
                  );
                })}
              </div>
            </fieldset>

            <div className={styles.formActions}>
              <Button type="submit" loading={saving}>Salvar</Button>
              <Button variant="ghost" onClick={() => setForm(null)} disabled={saving}>Cancelar</Button>
            </div>
          </form>
        </Section>
      )}

      <Section title="Perfis disponíveis" description="Perfis persistidos e disponíveis para consultas de Billing.">
        <Table aria-label="Perfis de Billing disponíveis">
          <TableHeader>
            <TableRow staticRow>
              <TableHead>Perfil</TableHead>
              <TableHead>Configuração</TableHead>
              <TableHead>Agrupamento</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Ações</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow staticRow>
                <TableState state="loading" colSpan={5}>Carregando perfis…</TableState>
              </TableRow>
            ) : profiles.length === 0 ? (
              <TableRow staticRow>
                <TableState state="empty" colSpan={5}>Nenhum perfil disponível.</TableState>
              </TableRow>
            ) : profiles.map((profile) => (
              <TableRow key={profile.id}>
                <TableCell>
                  <div className={styles.stack}>
                    <div className={styles.inlineMeta}>
                      <strong>{profile.name}</strong>
                      {profile.is_default && <Badge variant="info" appearance="subtle">Padrão</Badge>}
                    </div>
                    <span className={styles.secondaryText}>
                      {profile.description || (profile.is_system ? "Perfil de sistema" : "Sem descrição")}
                    </span>
                  </div>
                </TableCell>
                <TableCell>{profileSummary(profile)}</TableCell>
                <TableCell>{groupingLabels[profile.group_by]}</TableCell>
                <TableCell>
                  <StatusIndicator
                    status={profile.enabled ? "success" : "neutral"}
                    label={profile.enabled ? "Ativo" : "Inativo"}
                  />
                </TableCell>
                <TableCell>
                  <div className={styles.formActions}>
                    <Button size="sm" variant="ghost" onClick={() => edit(profile)} disabled={!profile.enabled}>
                      Editar
                    </Button>
                    {!profile.is_default && profile.enabled && (
                      <Button size="sm" variant="outline" onClick={() => void setDefault(profile)}>
                        Definir como padrão
                      </Button>
                    )}
                    {!profile.is_default && !profile.is_system && profile.enabled && (
                      <Button size="sm" variant="danger" onClick={() => void deactivate(profile)}>
                        Desativar
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>
    </>
  );
}
