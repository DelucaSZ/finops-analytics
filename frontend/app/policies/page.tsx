"use client";

import { useEffect, useState } from "react";
import { Check, RotateCcw, Save, SlidersHorizontal } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { api } from "@/lib/api";
import type { AwsAccount, Policy } from "@/lib/types";

export default function PoliciesPage() {
  const [scope, setScope] = useState<"global" | "account">("global");
  const [accountId, setAccountId] = useState<number | null>(null);
  const [accounts, setAccounts] = useState<AwsAccount[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { api<AwsAccount[]>("/accounts").then((data) => { setAccounts(data); if (data[0]) setAccountId(data[0].id); }).catch(() => undefined); }, []);
  useEffect(() => {
    if (scope === "account" && !accountId) return;
    setError("");
    api<Policy[]>(scope === "global" ? "/policies/global" : `/policies/accounts/${accountId}`)
      .then(setPolicies).catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar políticas"));
  }, [scope, accountId]);

  async function refresh() {
    setPolicies(await api<Policy[]>(scope === "global" ? "/policies/global" : `/policies/accounts/${accountId}`));
  }

  return (
    <>
      <PageHeader eyebrow="MOTOR DE REGRAS" title="Políticas de análise" description="Defina padrões universais e sobrescreva apenas os campos necessários por conta." />
      {error && <div className="alert error">{error}</div>}
      {message && <div className="alert success"><Check size={17} />{message}</div>}
      <section className="policy-scope-bar">
        <div className="segmented"><button className={scope === "global" ? "active" : ""} onClick={() => setScope("global")}>Padrão global</button><button className={scope === "account" ? "active" : ""} onClick={() => setScope("account")} disabled={!accounts.length}>Por conta</button></div>
        {scope === "account" && <select value={accountId || ""} onChange={(e) => setAccountId(Number(e.target.value))}>{accounts.map((account) => <option key={account.id} value={account.id}>{account.name} · {account.aws_account_id}</option>)}</select>}
        <p>{scope === "global" ? "Aplicado automaticamente a todas as contas sem sobrescrita." : "Campos não selecionados continuam herdando o padrão global."}</p>
      </section>
      <section className="policies-list">
        {policies.map((policy) => <PolicyCard key={`${scope}-${accountId}-${policy.rule_key}-${policy.override_fields.join(".")}`} policy={policy} scope={scope} accountId={accountId} onSaved={async (text) => { setMessage(text); await refresh(); }} />)}
      </section>
    </>
  );
}

function PolicyCard({ policy, scope, accountId, onSaved }: { policy: Policy; scope: "global" | "account"; accountId: number | null; onSaved: (message: string) => Promise<void> }) {
  const [enabled, setEnabled] = useState(policy.enabled);
  const [values, setValues] = useState<Record<string, unknown>>({ ...policy.config });
  const [overrides, setOverrides] = useState<Set<string>>(new Set(policy.override_fields));
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  function changeValue(key: string, original: unknown, raw: unknown) {
    let next: unknown = raw;
    if (typeof original === "number") next = Number(raw);
    if (Array.isArray(original)) next = String(raw).split(",").map((item) => item.trim()).filter(Boolean);
    setValues((current) => ({ ...current, [key]: next }));
  }

  async function save() {
    setBusy(true);
    try {
      const config = scope === "global" ? values : Object.fromEntries(Object.entries(values).filter(([key]) => overrides.has(key)));
      const enabledValue = scope === "global" || overrides.has("enabled") ? enabled : null;
      const path = scope === "global" ? `/policies/global/${policy.rule_key}` : `/policies/accounts/${accountId}/${policy.rule_key}`;
      await api(path, { method: "PUT", body: JSON.stringify({ enabled: enabledValue, config }) });
      await onSaved(`Política “${policy.name}” atualizada.`);
    } finally { setBusy(false); }
  }

  async function reset() {
    if (scope !== "account") return;
    setBusy(true);
    try { await api(`/policies/accounts/${accountId}/${policy.rule_key}`, { method: "DELETE" }); await onSaved(`“${policy.name}” voltou a herdar o padrão global.`); }
    finally { setBusy(false); }
  }

  return (
    <article className={`policy-card ${policy.implemented ? "" : "planned"}`}>
      <div className="policy-summary">
        <span className="policy-icon"><SlidersHorizontal size={19} /></span>
        <div><div className="policy-title-line"><h3>{policy.name}</h3>{!policy.implemented && <span className="coming-soon">Próxima etapa</span>}{scope === "account" && policy.inherited && <span className="inherited">Herdada</span>}</div><p>{policy.description}</p></div>
        <label className="switch"><input aria-label={`Ativar política ${policy.name}`} type="checkbox" checked={enabled} onChange={(e) => { setEnabled(e.target.checked); if (scope === "account") setOverrides(new Set([...overrides, "enabled"])); }} disabled={!policy.implemented} /><span /></label>
        <button className="button small ghost" onClick={() => setOpen(!open)}>{open ? "Fechar" : "Configurar"}</button>
      </div>
      {open && (
        <div className="policy-editor">
          <div className="policy-fields">
            {Object.entries(values).map(([key, value]) => (
              <div className="policy-field" key={key}>
                {scope === "account" && <label className="override-check" title="Sobrescrever este campo"><input type="checkbox" checked={overrides.has(key)} onChange={(e) => { const next = new Set(overrides); e.target.checked ? next.add(key) : next.delete(key); setOverrides(next); }} /></label>}
                <label><span>{humanize(key)}</span>{renderInput(key, value, (raw) => changeValue(key, value, raw), scope === "account" && !overrides.has(key))}</label>
              </div>
            ))}
          </div>
          <div className="policy-actions">{scope === "account" && <button className="button ghost" onClick={() => void reset()} disabled={busy}><RotateCcw size={15} /> Restaurar herança</button>}<button className="button primary" onClick={() => void save()} disabled={busy || !policy.implemented}><Save size={15} /> {busy ? "Salvando…" : "Salvar política"}</button></div>
        </div>
      )}
    </article>
  );
}

function renderInput(key: string, value: unknown, onChange: (value: unknown) => void, disabled: boolean) {
  if (typeof value === "boolean") return <select value={String(value)} onChange={(e) => onChange(e.target.value === "true")} disabled={disabled}><option value="true">Sim</option><option value="false">Não</option></select>;
  if (typeof value === "number") return <input type="number" value={value} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
  if (Array.isArray(value)) return <input value={value.join(", ")} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
  if (typeof value === "object" && value !== null) return <ObjectEditor value={value as Record<string, unknown>} onChange={onChange} disabled={disabled} />;
  return <input value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} disabled={disabled} />;
}

function ObjectEditor({ value, onChange, disabled }: { value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void; disabled: boolean }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [invalid, setInvalid] = useState(false);
  return <><textarea className={invalid ? "invalid" : ""} rows={4} value={text} disabled={disabled} onChange={(event) => { const next = event.target.value; setText(next); try { const parsed = JSON.parse(next); if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error(); setInvalid(false); onChange(parsed); } catch { setInvalid(true); } }} />{invalid && <small className="field-error">JSON inválido</small>}</>;
}

function humanize(value: string) {
  const labels: Record<string, string> = { minimum_age_days: "Idade mínima (dias)", minimum_monthly_savings_usd: "Economia mínima mensal (USD)", monthly_price_per_gb: "Preço por GB/mês", excluded_tag_keys: "Tags de exclusão", monthly_cost_usd: "Custo mensal unitário (USD)", retention_days: "Retenção (dias)", preserve_last_per_volume: "Preservar últimos por volume", preserve_ami_snapshots: "Preservar snapshots de AMI", minimum_stopped_days: "Tempo mínimo desligada (dias)", include_unknown_stop_time: "Incluir tempo de parada desconhecido", timezone: "Fuso horário", business_days: "Dias úteis", business_hours_start: "Início do expediente", business_hours_end: "Fim do expediente", environment_tag_keys: "Tags de ambiente", nonproduction_values: "Valores de não produção", lookback_days: "Janela de análise (dias)", maximum_requests: "Máximo de requisições", maximum_average_cpu_percent: "CPU média máxima (%)", maximum_connections: "Máximo de conexões", required_tags: "Tags obrigatórias", resource_types: "Tipos de recurso", baseline_days: "Linha de base (dias)", comparison_days: "Período comparado (dias)", minimum_growth_percent: "Crescimento mínimo (%)", minimum_delta_usd: "Aumento mínimo (USD)", minimum_current_spend_usd: "Gasto atual mínimo (USD)" };
  return labels[value] || value.replaceAll("_", " ");
}
