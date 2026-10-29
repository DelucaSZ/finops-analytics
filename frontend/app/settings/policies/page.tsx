"use client";

import { useEffect, useState, type ReactNode } from "react";
import { RotateCcw, Save, SlidersHorizontal } from "lucide-react";
import { PageHeader } from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  EmptyState,
  Input,
  Select,
  Switch,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { providerLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import { canManagePolicies } from "@/lib/settings-navigation.mjs";
import type { CloudAccount, Policy, ProviderCapabilities } from "@/lib/types";
import styles from "./page.module.css";

type CurrentUser = { role: string };
type AwsPolicyAccount = CloudAccount & { aws_configuration: NonNullable<CloudAccount["aws_configuration"]> };

type SegmentedOption = {
  value: string;
  label: ReactNode;
  disabled?: boolean;
};

export default function PoliciesPage() {
  const [provider, setProvider] = useState("aws");
  const [scope, setScope] = useState<"global" | "account">("global");
  const [accountId, setAccountId] = useState<number | null>(null);
  const [accounts, setAccounts] = useState<AwsPolicyAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [role, setRole] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const canManage = canManagePolicies(role);
  const providerCapabilities = capabilities.find((item) => item.provider === provider);
  const availableProviders = capabilities.filter((item) => item.registration);

  useEffect(() => {
    let active = true;
    Promise.all([
      api<CloudAccount[]>("/cloud-accounts"),
      api<ProviderCapabilities[]>("/cloud-accounts/capabilities"),
      api<CurrentUser>("/auth/me"),
    ])
      .then(([data, providerCapabilities, user]) => {
        if (!active) return;
        const awsAccounts = data.filter(
          (account): account is AwsPolicyAccount =>
            account.provider === "aws" && account.aws_configuration !== null,
        );
        setAccounts(awsAccounts);
        setCapabilities(providerCapabilities);
        setRole(user.role);
        if (awsAccounts[0]) setAccountId(awsAccounts[0].aws_configuration.id);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Falha ao carregar configurações de políticas");
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!providerCapabilities) return;
    if (!providerCapabilities.finops_policies) {
      setPolicies([]);
      setError("");
      return;
    }
    if (provider !== "aws") {
      setPolicies([]);
      return;
    }
    if (scope === "account" && !accountId) return;
    setError("");
    api<Policy[]>(scope === "global" ? "/policies/global" : `/policies/accounts/${accountId}`)
      .then(setPolicies)
      .catch((err) => setError(err instanceof Error ? err.message : "Falha ao carregar políticas"));
  }, [provider, providerCapabilities, scope, accountId]);

  async function refresh() {
    if (!providerCapabilities?.finops_policies || provider !== "aws") return;
    setPolicies(
      await api<Policy[]>(
        scope === "global" ? "/policies/global" : `/policies/accounts/${accountId}`,
      ),
    );
  }

  return (
    <div className={styles.page}>
      <PageHeader
        title="Políticas"
        description="Configure regras de análise FinOps somente onde o provider possui suporte operacional implementado."
        metadata={<span>Configurações · Políticas</span>}
      />

      {error && <Alert variant="danger" title="Não foi possível carregar políticas" description={error} />}
      {message && <Alert variant="success" title={message} />}

      <div className={styles.scopeStack}>
        <div className={styles.scopeRow}>
          <SegmentedButtons
            label="Cloud das políticas"
            value={provider}
            options={availableProviders.map((item) => ({ value: item.provider, label: item.label }))}
            onValueChange={(nextProvider) => {
              setProvider(nextProvider);
              setScope("global");
              setMessage("");
            }}
          />
          <p className={styles.scopeDescription}>
            Políticas nesta área são regras FinOps do Aven; não são políticas IAM de autenticação.
          </p>
        </div>

        {providerCapabilities?.finops_policies && (
          <div className={styles.scopeRow}>
            <SegmentedButtons
              label="Escopo das políticas"
              value={scope}
              options={[
                { value: "global", label: "Padrão global AWS" },
                { value: "account", label: "Por conta AWS", disabled: !accounts.length },
              ]}
              onValueChange={(nextScope) => setScope(nextScope as "global" | "account")}
            />
            {scope === "account" && (
              <div className={styles.accountSelect}>
                <Select
                  aria-label="Conta AWS"
                  value={accountId === null ? "" : String(accountId)}
                  onChange={(event) => setAccountId(Number(event.target.value))}
                  options={accounts.map((account) => ({
                    value: String(account.aws_configuration.id),
                    label: `${account.name} · ${account.native_account_id}`,
                  }))}
                />
              </div>
            )}
            <p className={styles.scopeDescription}>
              {scope === "global"
                ? "Aplicado às contas AWS sem sobrescrita específica."
                : "Campos não selecionados continuam herdando o padrão global AWS."}
            </p>
          </div>
        )}
      </div>

      {providerCapabilities && !providerCapabilities.finops_policies ? (
        <EmptyState
          icon={<SlidersHorizontal {...iconDefaults} />}
          title={`Políticas de análise ${providerCapabilities.label} ainda não disponíveis`}
          description="O cadastro e o teste de conexão podem estar disponíveis sem que existam coletor e regras FinOps para este provider. Nenhuma regra AWS é aplicada a esta conta."
        />
      ) : (
        <section className={styles.policiesList} aria-label="Políticas FinOps">
          {policies.map((policy) => (
            <PolicyCard
              key={`${scope}-${accountId}-${policy.rule_key}-${policy.override_fields.join(".")}`}
              policy={policy}
              scope={scope}
              accountId={accountId}
              canManage={canManage}
              onSaved={async (text) => {
                setMessage(text);
                await refresh();
              }}
            />
          ))}
        </section>
      )}
    </div>
  );
}

function SegmentedButtons({
  label,
  value,
  options,
  onValueChange,
}: {
  label: string;
  value: string;
  options: SegmentedOption[];
  onValueChange: (value: string) => void;
}) {
  return (
    <div className={styles.segmentedGroup} role="group" aria-label={label}>
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <Button
            key={option.value}
            size="sm"
            variant={selected ? "secondary" : "ghost"}
            aria-pressed={selected}
            disabled={option.disabled}
            onClick={() => onValueChange(option.value)}
          >
            {option.label}
          </Button>
        );
      })}
    </div>
  );
}

function PolicyCard({ policy, scope, accountId, canManage, onSaved }: { policy: Policy; scope: "global" | "account"; accountId: number | null; canManage: boolean; onSaved: (message: string) => Promise<void> }) {
  const [enabled, setEnabled] = useState(policy.enabled);
  const [values, setValues] = useState<Record<string, unknown>>({ ...policy.config });
  const [overrides, setOverrides] = useState<Set<string>>(new Set(policy.override_fields));
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  function changeValue(key: string, original: unknown, raw: unknown) {
    if (!canManage) return;
    let next: unknown = raw;
    if (typeof original === "number") next = Number(raw);
    if (Array.isArray(original)) next = String(raw).split(",").map((item) => item.trim()).filter(Boolean);
    setValues((current) => ({ ...current, [key]: next }));
  }

  async function save() {
    if (!canManage) return;
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
    if (!canManage || scope !== "account") return;
    setBusy(true);
    try {
      await api(`/policies/accounts/${accountId}/${policy.rule_key}`, { method: "DELETE" });
      await onSaved(`“${policy.name}” voltou a herdar o padrão global.`);
    } finally { setBusy(false); }
  }

  return (
    <Card className={`${styles.policyCard} ${policy.implemented ? "" : styles.plannedCard}`}>
      <div className={styles.policySummary}>
        <span className={styles.policyIcon}><SlidersHorizontal {...iconDefaults} /></span>
        <div className={styles.policyCopy}>
          <div className={styles.policyTitleLine}>
            <h3 className={styles.policyTitle}>{policy.name}</h3>
            <Badge variant="info">{providerLabel(policy.provider)}</Badge>
            {!policy.implemented && <Badge variant="warning">Próxima etapa</Badge>}
            {scope === "account" && policy.inherited && <Badge variant="neutral">Herdada</Badge>}
          </div>
          <p className={styles.policyDescription}>{policy.description}</p>
        </div>
        <div className={styles.policySummaryActions}>
          <Switch
            aria-label={(canManage ? "Ativar política " : "Status da política ") + policy.name}
            checked={enabled}
            onCheckedChange={(checked) => {
              if (!canManage) return;
              setEnabled(checked);
              if (scope === "account") setOverrides(new Set([...overrides, "enabled"]));
            }}
            disabled={!policy.implemented || !canManage}
          />
          <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? "Fechar" : canManage ? "Configurar" : "Visualizar"}
          </Button>
        </div>
      </div>

      {open && (
        <div className={styles.policyEditor}>
          <div className={styles.policyFields}>
            {Object.entries(values).map(([key, value]) => {
              const fieldDisabled = !canManage || (scope === "account" && !overrides.has(key));
              return (
                <div className={styles.policyField} key={key}>
                  {scope === "account" && (
                    <Checkbox
                      aria-label={`Sobrescrever ${humanize(key)}`}
                      checked={overrides.has(key)}
                      disabled={!canManage}
                      onChange={(event) => {
                        if (!canManage) return;
                        const next = new Set(overrides);
                        event.target.checked ? next.add(key) : next.delete(key);
                        setOverrides(next);
                      }}
                    />
                  )}
                  <div className={styles.policyFieldControl}>
                    {renderInput(key, value, (raw) => changeValue(key, value, raw), fieldDisabled)}
                  </div>
                </div>
              );
            })}
          </div>

          {canManage && (
            <div className={styles.policyActions}>
              {scope === "account" && (
                <Button
                  variant="ghost"
                  leadingIcon={<RotateCcw {...iconDefaults} />}
                  onClick={() => void reset()}
                  disabled={busy}
                >
                  Restaurar herança
                </Button>
              )}
              <Button
                variant="primary"
                leadingIcon={<Save {...iconDefaults} />}
                onClick={() => void save()}
                loading={busy}
                disabled={!policy.implemented}
              >
                Salvar política
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function renderInput(key: string, value: unknown, onChange: (value: unknown) => void, disabled: boolean) {
  const label = humanize(key);
  if (typeof value === "boolean") {
    return (
      <Select
        label={label}
        value={String(value)}
        onChange={(event) => onChange(event.target.value === "true")}
        disabled={disabled}
        options={[
          { value: "true", label: "Sim" },
          { value: "false", label: "Não" },
        ]}
      />
    );
  }
  if (typeof value === "number") {
    return <Input label={label} type="number" value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} />;
  }
  if (Array.isArray(value)) {
    return <Input label={label} value={value.join(", ")} onChange={(event) => onChange(event.target.value)} disabled={disabled} />;
  }
  if (typeof value === "object" && value !== null) {
    return <ObjectEditor label={label} value={value as Record<string, unknown>} onChange={onChange} disabled={disabled} />;
  }
  return <Input label={label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} disabled={disabled} />;
}

function ObjectEditor({ label, value, onChange, disabled }: { label: string; value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void; disabled: boolean }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [invalid, setInvalid] = useState(false);
  return (
    <Textarea
      label={label}
      rows={4}
      value={text}
      disabled={disabled}
      error={invalid ? "JSON inválido" : undefined}
      onChange={(event) => {
        const next = event.target.value;
        setText(next);
        try {
          const parsed = JSON.parse(next);
          if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
          setInvalid(false);
          onChange(parsed);
        } catch {
          setInvalid(true);
        }
      }}
    />
  );
}

function humanize(value: string) {
  const labels: Record<string, string> = { minimum_age_days: "Idade mínima (dias)", minimum_monthly_savings_usd: "Economia mínima mensal (USD)", monthly_price_per_gb: "Preço por GB/mês", excluded_tag_keys: "Tags de exclusão", monthly_cost_usd: "Custo mensal unitário (USD)", retention_days: "Retenção (dias)", preserve_last_per_volume: "Preservar últimos por volume", preserve_ami_snapshots: "Preservar snapshots de AMI", minimum_stopped_days: "Tempo mínimo desligada (dias)", include_unknown_stop_time: "Incluir tempo de parada desconhecido", timezone: "Fuso horário", business_days: "Dias úteis", business_hours_start: "Início do expediente", business_hours_end: "Fim do expediente", environment_tag_keys: "Tags de ambiente", nonproduction_values: "Valores de não produção", lookback_days: "Janela de análise (dias)", maximum_requests: "Máximo de requisições", maximum_average_cpu_percent: "CPU média máxima (%)", maximum_connections: "Máximo de conexões", required_tags: "Tags obrigatórias", resource_types: "Tipos de recurso", baseline_days: "Linha de base (dias)", comparison_days: "Período comparado", minimum_growth_percent: "Crescimento mínimo (%)", minimum_delta_usd: "Aumento mínimo (USD)", minimum_current_spend_usd: "Gasto atual mínimo (USD)" };
  return labels[value] || value.replaceAll("_", " ");
}
