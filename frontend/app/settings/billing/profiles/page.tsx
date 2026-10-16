"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Pencil, Plus, Star, XCircle } from "lucide-react";
import { PageHeader } from "@/components/page-header";
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
    <div className="billing-profiles-page">
      <PageHeader
        eyebrow="CONFIGURAÇÕES · BILLING"
        title="Perfis de Billing"
        description="Salve metodologias reutilizáveis para consultas ao AWS Cost Explorer. Período e contas continuam sendo escolhidos na consulta."
        actions={
          <button className="button primary" onClick={() => setForm({ ...emptyForm })}>
            <Plus size={16} /> Novo perfil
          </button>
        }
      />

      {error && <div className="alert error" role="alert">{error}</div>}
      {success && <div className="alert success"><Check size={17} />{success}</div>}

      {form && (
        <section className="panel billing-profile-form-panel">
          <h2>{form.id ? "Editar perfil" : "Novo perfil"}</h2>
          <form onSubmit={submit} className="form-grid">
            <label>
              <span>Nome</span>
              <input
                required
                maxLength={120}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
            </label>
            <label>
              <span>Descrição</span>
              <input
                maxLength={1000}
                value={form.description ?? ""}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
            </label>
            <label>
              <span>Métrica</span>
              <select
                value={form.metric}
                onChange={(event) => setForm({ ...form, metric: event.target.value as BillingMetric })}
              >
                {Object.entries(metricLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Granularidade</span>
              <select
                value={form.granularity}
                onChange={(event) => setForm({ ...form, granularity: event.target.value as BillingGranularity })}
              >
                {Object.entries(granularityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>
              <span>Agrupamento padrão</span>
              <select
                value={form.group_by}
                onChange={(event) => setForm({ ...form, group_by: event.target.value as BillingGroupBy })}
              >
                {Object.entries(groupingLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            {!form.id && (
              <label>
                <span>Padrão</span>
                <input
                  type="checkbox"
                  checked={Boolean(form.is_default)}
                  onChange={(event) => setForm({ ...form, is_default: event.target.checked })}
                /> Definir como padrão
              </label>
            )}
            <fieldset>
              <legend>Excluir tipos de registro</legend>
              <div className="checkbox-list">
                {RECORD_TYPES.map((recordType) => {
                  const checked = form.exclude_record_types.includes(recordType);
                  return (
                    <label key={recordType}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(event) => {
                          const next = event.target.checked
                            ? [...form.exclude_record_types, recordType]
                            : form.exclude_record_types.filter((item) => item !== recordType);
                          setForm({ ...form, exclude_record_types: next });
                        }}
                      />
                      {recordType}
                    </label>
                  );
                })}
              </div>
            </fieldset>
            <div className="actions">
              <button className="button primary" type="submit" disabled={saving}>
                {saving ? "Salvando…" : "Salvar"}
              </button>
              <button className="button ghost" type="button" onClick={() => setForm(null)} disabled={saving}>
                Cancelar
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel billing-profiles-panel">
        <h2>Perfis disponíveis</h2>
        {loading ? (
          <p role="status">Carregando perfis…</p>
        ) : profiles.length === 0 ? (
          <p>Nenhum perfil disponível.</p>
        ) : (
          <div className="table-wrap billing-profiles-table-wrap">
            <table className="billing-profiles-table">
              <colgroup>
                <col className="billing-col-profile" />
                <col className="billing-col-configuration" />
                <col className="billing-col-grouping" />
                <col className="billing-col-status" />
                <col className="billing-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">Perfil</th>
                  <th scope="col">Configuração</th>
                  <th scope="col">Agrupamento</th>
                  <th scope="col">Status</th>
                  <th scope="col">Ações</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((profile) => (
                  <tr key={profile.id}>
                    <td>
                      <div className="billing-profile-name">
                        <strong>{profile.name}</strong>
                        {profile.is_default && <span className="badge">Padrão</span>}
                      </div>
                      <div className="muted billing-profile-description">
                        {profile.description || (profile.is_system ? "Perfil de sistema" : "Sem descrição")}
                      </div>
                    </td>
                    <td className="billing-profile-configuration">{profileSummary(profile)}</td>
                    <td className="billing-profile-grouping">{groupingLabels[profile.group_by]}</td>
                    <td className="billing-profile-status">{profile.enabled ? "Ativo" : "Inativo"}</td>
                    <td>
                      <div className="actions billing-profile-actions">
                        <button className="button ghost" onClick={() => edit(profile)} disabled={!profile.enabled}>
                          <Pencil size={15} /> Editar
                        </button>
                        {!profile.is_default && profile.enabled && (
                          <button className="button ghost" onClick={() => void setDefault(profile)}>
                            <Star size={15} /> Definir como padrão
                          </button>
                        )}
                        {!profile.is_default && !profile.is_system && profile.enabled && (
                          <button className="button ghost" onClick={() => void deactivate(profile)}>
                            <XCircle size={15} /> Desativar
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
