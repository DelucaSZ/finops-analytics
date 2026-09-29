"use client";

import { FormEvent, useEffect, useState } from "react";
import { Building2, Check, Copy, Play, Plus, RefreshCw, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { api, formatDate } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import {
  canManageCloudAccounts,
  canRunCloudAnalysis,
} from "@/lib/settings-navigation.mjs";
import type { CloudAccount, Scan } from "@/lib/types";

type CurrentUser = { role: string };

const emptyForm = {
  name: "",
  aws_account_id: "",
  role_arn: "",
  external_id: "",
  regions: "sa-east-1",
  is_management_account: false,
  schedule_enabled: false,
  scan_interval_hours: 24,
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [role, setRole] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...emptyForm });
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<number | "create" | null>(null);
  const canManageAccounts = canManageCloudAccounts(role);
  const canAnalyze = canRunCloudAnalysis(role);

  async function load() {
    try { setAccounts(await api<CloudAccount[]>("/cloud-accounts")); }
    catch (err) { setError(err instanceof Error ? err.message : "Falha ao carregar contas"); }
  }

  useEffect(() => {
    let active = true;
    Promise.all([api<CloudAccount[]>("/cloud-accounts"), api<CurrentUser>("/auth/me")])
      .then(([items, user]) => {
        if (!active) return;
        setAccounts(items);
        setRole(user.role);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar contas");
      });
    return () => { active = false; };
  }, []);

  async function openCreateForm() {
    if (!canManageAccounts) return;
    setError("");
    try {
      const generated = await api<{ external_id: string }>("/cloud-accounts/aws/external-id");
      setForm({ ...emptyForm, external_id: generated.external_id });
      setShowForm(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao gerar External ID");
    }
  }

  async function createAccount(event: FormEvent) {
    event.preventDefault();
    if (!canManageAccounts) return;
    setBusy("create");
    setError("");
    try {
      await api<CloudAccount>("/cloud-accounts", {
        method: "POST",
        body: JSON.stringify({
          provider: "aws",
          native_account_id: form.aws_account_id,
          name: form.name,
          enabled: true,
          configuration: {
            role_arn: form.role_arn,
            external_id: form.external_id,
            regions: form.regions.split(",").map((item) => item.trim()).filter(Boolean),
            is_management_account: form.is_management_account,
            schedule_enabled: form.schedule_enabled,
            scan_interval_hours: form.scan_interval_hours,
          },
        }),
      });
      setForm({ ...emptyForm });
      setShowForm(false);
      setMessage("Conta cadastrada. Agora valide a conexão.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao cadastrar");
    } finally {
      setBusy(null);
    }
  }

  async function test(account: CloudAccount) {
    if (!canManageAccounts) return;
    setBusy(account.id);
    setError("");
    setMessage("");
    try {
      const result = await api<{ ok: boolean; error?: string }>(
        `/cloud-accounts/${account.id}/test-connection`,
        { method: "POST" },
      );
      if (!result.ok) throw new Error(result.error || "A conexão não pôde ser validada");
      setMessage(`Conexão com ${account.name} validada com sucesso.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha no teste");
      await load();
    } finally {
      setBusy(null);
    }
  }

  async function scan(account: CloudAccount) {
    if (!canAnalyze) return;
    const legacyAwsId = account.aws_configuration?.id;
    if (account.provider !== "aws" || !legacyAwsId) {
      setError(`Análise manual ainda não está disponível para ${providerLabel(account.provider)}.`);
      return;
    }
    setBusy(account.id);
    setError("");
    setMessage("");
    try {
      await api<Scan>("/scans", {
        method: "POST",
        body: JSON.stringify({ account_id: legacyAwsId }),
      });
      setMessage(`Análise de ${account.name} adicionada à fila.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Falha ao iniciar análise");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="CONFIGURAÇÕES · CONTAS"
        title="Contas"
        description="Gerencie as contas cloud conectadas ao DeepOps. AWS continua disponível pela interface; a integração OCI por API Key já pode ser administrada pela API e ganhará formulário unificado na Etapa 19."
        actions={canManageAccounts ? <button className="button primary" onClick={() => void openCreateForm()}><Plus size={17} /> Adicionar conta AWS</button> : undefined}
      />
      {error && <div className="alert error"><X size={17} />{error}</div>}
      {message && <div className="alert success"><Check size={17} />{message}</div>}

      {showForm && canManageAccounts && (
        <section className="panel account-form-panel">
          <div className="panel-heading"><div><span className="eyebrow">NOVA CONEXÃO</span><h2>Cadastrar conta AWS</h2></div><button className="icon-button" aria-label="Fechar cadastro de conta AWS" onClick={() => setShowForm(false)}><X size={18} /></button></div>
          <form className="form-grid" onSubmit={createAccount}>
            <label>Nome da conta<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Produção" required /></label>
            <label>AWS Account ID<input value={form.aws_account_id} onChange={(e) => setForm({ ...form, aws_account_id: e.target.value.replace(/\D/g, "").slice(0, 12) })} placeholder="123456789012" pattern="[0-9]{12}" required /></label>
            <label className="span-2">Role ARN<input value={form.role_arn} onChange={(e) => setForm({ ...form, role_arn: e.target.value })} placeholder="arn:aws:iam::123456789012:role/NuvemIQReadOnly" required /></label>
            <label className="span-2">External ID<div className="input-action"><input value={form.external_id} onChange={(e) => setForm({ ...form, external_id: e.target.value })} required /><button type="button" title="Copiar" onClick={() => void navigator.clipboard.writeText(form.external_id)}><Copy size={16} /></button></div><small>Use exatamente este valor ao criar a role na conta-alvo.</small></label>
            <label>Regiões<input value={form.regions} onChange={(e) => setForm({ ...form, regions: e.target.value })} placeholder="sa-east-1, us-east-1" required /><small>Separadas por vírgula.</small></label>
            <label>Intervalo de análise<select value={form.scan_interval_hours} onChange={(e) => setForm({ ...form, scan_interval_hours: Number(e.target.value) })}><option value={12}>A cada 12 horas</option><option value={24}>Diariamente</option><option value={168}>Semanalmente</option></select></label>
            <label className="check-label"><input type="checkbox" checked={form.is_management_account} onChange={(e) => setForm({ ...form, is_management_account: e.target.checked })} /> Conta management/payer</label>
            <label className="check-label"><input type="checkbox" checked={form.schedule_enabled} onChange={(e) => setForm({ ...form, schedule_enabled: e.target.checked })} /> Ativar análises agendadas</label>
            <div className="form-actions span-2"><button type="button" className="button ghost" onClick={() => setShowForm(false)}>Cancelar</button><button className="button primary" disabled={busy === "create"}>{busy === "create" ? "Salvando…" : "Cadastrar conta AWS"}</button></div>
          </form>
        </section>
      )}

      <section className="accounts-grid">
        {accounts.map((account) => {
          const aws = account.aws_configuration;
          const oci = account.oci_configuration;
          const connectionSupported = Boolean(aws || oci);
          return (
            <article className="account-card" key={account.id}>
              <div className="account-top"><span className="account-icon"><Building2 size={21} /></span><div><h3>{account.name}</h3><code>{providerLabel(account.provider)} · {account.native_account_id}</code></div><StatusBadge value={account.connection_status} /></div>
              {aws ? <dl><div><dt>Role</dt><dd title={aws.role_arn}>{aws.role_arn.split("/").pop()}</dd></div><div><dt>Regiões</dt><dd>{aws.regions.join(", ")}</dd></div><div><dt>Agendamento</dt><dd>{aws.schedule_enabled ? `A cada ${aws.scan_interval_hours}h` : "Desativado"}</dd></div><div><dt>Último teste</dt><dd>{formatDate(account.last_connection_test_at)}</dd></div></dl> : oci ? <dl><div><dt>Usuário OCI</dt><dd title={oci.user_ocid}>{oci.user_ocid}</dd></div><div><dt>Região de conexão</dt><dd>{oci.region}</dd></div><div><dt>Escopo</dt><dd>{oci.compartment_ocids.length ? `${oci.compartment_ocids.length} compartment(s)` : oci.include_root_compartment ? "Tenancy root" : "Nenhum compartment"}</dd></div><div><dt>Credencial</dt><dd>{oci.credentials_configured ? "API Key configurada" : "Não configurada"}</dd></div><div><dt>Último teste</dt><dd>{formatDate(account.last_connection_test_at)}</dd></div></dl> : <p>Provider cadastrado sem integração operacional disponível nesta etapa.</p>}
              {account.last_error && <div className="account-error" title={account.last_error}>{account.last_error}</div>}
              {(canManageAccounts || canAnalyze) && <div className="account-actions">{canManageAccounts && connectionSupported && <button className="button ghost" onClick={() => void test(account)} disabled={busy === account.id}><RefreshCw size={15} className={busy === account.id ? "spin" : ""} /> Testar conexão</button>}{canAnalyze && aws && <button className="button primary" onClick={() => void scan(account)} disabled={busy === account.id || account.connection_status !== "connected"}><Play size={15} /> Analisar</button>}</div>}
            </article>
          );
        })}
        {!accounts.length && !showForm && canManageAccounts && <button className="account-card add-account" onClick={() => void openCreateForm()}><Plus size={25} /><strong>Adicionar a primeira conta AWS</strong><span>Configure uma role somente leitura.</span></button>}
        {!accounts.length && !showForm && role && !canManageAccounts && <article className="account-card"><div className="account-top"><span className="account-icon"><Building2 size={21} /></span><div><h3>Nenhuma conta cadastrada</h3><code>Somente leitura</code></div></div><p>O cadastro e a configuração de contas são realizados por administradores.</p></article>}
      </section>
    </>
  );
}
