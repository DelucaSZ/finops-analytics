"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
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
  const t = useTranslations("settings.policies");
  const [provider, setProvider] = useState("aws");
  const [scope, setScope] = useState<"global" | "account">("global");
  const [accountId, setAccountId] = useState<number | null>(null);
  const [accounts, setAccounts] = useState<AwsPolicyAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [role, setRole] = useState("");
  const [message, setMessage] = useState<{ kind: "updated" | "reset"; name: string } | null>(null);
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
        if (active) setError(err instanceof Error ? err.message : "ERR_POLICIES_SETTINGS_LOAD");
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
      .catch((err) => setError(err instanceof Error ? err.message : "ERR_POLICIES_LOAD"));
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
        title={t("title")}
        description={t("description")}
        metadata={<span>{t("metadata")}</span>}
      />

      {error && <Alert variant="danger" title={t("loadError")} description={error === "ERR_POLICIES_SETTINGS_LOAD" ? t("settingsLoadFailed") : error === "ERR_POLICIES_LOAD" ? t("loadError") : error} />}
      {message && <Alert variant="success" title={message.kind === "updated" ? t("updated", {name: message.name}) : t("resetSuccess", {name: message.name})} />}

      <div className={styles.scopeStack}>
        <div className={styles.scopeRow}>
          <SegmentedButtons
            label={t("policyCloud")}
            value={provider}
            options={availableProviders.map((item) => ({ value: item.provider, label: item.label }))}
            onValueChange={(nextProvider) => {
              setProvider(nextProvider);
              setScope("global");
              setMessage(null);
            }}
          />
          <p className={styles.scopeDescription}>
            {t("iamNote")}
          </p>
        </div>

        {providerCapabilities?.finops_policies && (
          <div className={styles.scopeRow}>
            <SegmentedButtons
              label={t("scope")}
              value={scope}
              options={[
                { value: "global", label: t("globalAws") },
                { value: "account", label: t("awsAccountScope"), disabled: !accounts.length },
              ]}
              onValueChange={(nextScope) => setScope(nextScope as "global" | "account")}
            />
            {scope === "account" && (
              <div className={styles.accountSelect}>
                <Select
                  aria-label={t("awsAccount")}
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
                ? t("globalScopeDescription")
                : t("accountScopeDescription")}
            </p>
          </div>
        )}
      </div>

      {providerCapabilities && !providerCapabilities.finops_policies ? (
        <EmptyState
          icon={<SlidersHorizontal {...iconDefaults} />}
          title={t("unavailableTitle", {provider: providerCapabilities.label})}
          description={t("unavailableDescription")}
        />
      ) : (
        <section className={styles.policiesList} aria-label={t("listLabel")}>
          {policies.map((policy) => (
            <PolicyCard
              key={`${scope}-${accountId}-${policy.rule_key}-${policy.override_fields.join(".")}`}
              policy={policy}
              scope={scope}
              accountId={accountId}
              canManage={canManage}
              onSaved={async (kind, name) => {
                setMessage({kind, name});
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

function PolicyCard({ policy, scope, accountId, canManage, onSaved }: { policy: Policy; scope: "global" | "account"; accountId: number | null; canManage: boolean; onSaved: (kind: "updated" | "reset", name: string) => Promise<void> }) {
  const t = useTranslations("settings.policies");
  const fieldLabels: Record<string, string> = {
    minimum_age_days: t("fields.minimumAgeDays"),
    minimum_monthly_savings_usd: t("fields.minimumMonthlySavingsUsd"),
    monthly_price_per_gb: t("fields.monthlyPricePerGb"),
    excluded_tag_keys: t("fields.excludedTagKeys"),
    monthly_cost_usd: t("fields.monthlyCostUsd"),
    retention_days: t("fields.retentionDays"),
    preserve_last_per_volume: t("fields.preserveLastPerVolume"),
    preserve_ami_snapshots: t("fields.preserveAmiSnapshots"),
    minimum_stopped_days: t("fields.minimumStoppedDays"),
    include_unknown_stop_time: t("fields.includeUnknownStopTime"),
    timezone: t("fields.timezone"),
    business_days: t("fields.businessDays"),
    business_hours_start: t("fields.businessHoursStart"),
    business_hours_end: t("fields.businessHoursEnd"),
    environment_tag_keys: t("fields.environmentTagKeys"),
    nonproduction_values: t("fields.nonproductionValues"),
    lookback_days: t("fields.lookbackDays"),
    maximum_requests: t("fields.maximumRequests"),
    maximum_average_cpu_percent: t("fields.maximumAverageCpuPercent"),
    maximum_connections: t("fields.maximumConnections"),
    required_tags: t("fields.requiredTags"),
    resource_types: t("fields.resourceTypes"),
    baseline_days: t("fields.baselineDays"),
    comparison_days: t("fields.comparisonDays"),
    minimum_growth_percent: t("fields.minimumGrowthPercent"),
    minimum_delta_usd: t("fields.minimumDeltaUsd"),
    minimum_current_spend_usd: t("fields.minimumCurrentSpendUsd"),
  };
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
      await onSaved("updated", policy.name);
    } finally { setBusy(false); }
  }

  async function reset() {
    if (!canManage || scope !== "account") return;
    setBusy(true);
    try {
      await api(`/policies/accounts/${accountId}/${policy.rule_key}`, { method: "DELETE" });
      await onSaved("reset", policy.name);
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
            {!policy.implemented && <Badge variant="warning">{t("planned")}</Badge>}
            {scope === "account" && policy.inherited && <Badge variant="neutral">{t("inherited")}</Badge>}
          </div>
          <p className={styles.policyDescription}>{policy.description}</p>
        </div>
        <div className={styles.policySummaryActions}>
          <Switch
            aria-label={canManage ? t("enablePolicy", {name: policy.name}) : t("statusPolicy", {name: policy.name})}
            checked={enabled}
            onCheckedChange={(checked) => {
              if (!canManage) return;
              setEnabled(checked);
              if (scope === "account") setOverrides(new Set([...overrides, "enabled"]));
            }}
            disabled={!policy.implemented || !canManage}
          />
          <Button variant="ghost" size="sm" onClick={() => setOpen(!open)} aria-expanded={open}>
            {open ? t("close") : canManage ? t("configure") : t("view")}
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
                      aria-label={t("override", {field: fieldLabels[key] ?? humanize(key)})}
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
                    {renderInput(key, value, (raw) => changeValue(key, value, raw), fieldDisabled, fieldLabels, {yes: t("yes"), no: t("no"), invalidJson: t("invalidJson")})}
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
                  {t("restoreInheritance")}
                </Button>
              )}
              <Button
                variant="primary"
                leadingIcon={<Save {...iconDefaults} />}
                onClick={() => void save()}
                loading={busy}
                disabled={!policy.implemented}
              >
                {t("savePolicy")}
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

function renderInput(key: string, value: unknown, onChange: (value: unknown) => void, disabled: boolean, fieldLabels: Record<string, string>, words: {yes: string; no: string; invalidJson: string}) {
  const label = fieldLabels[key] ?? humanize(key);
  if (typeof value === "boolean") {
    return (
      <Select
        label={label}
        value={String(value)}
        onChange={(event) => onChange(event.target.value === "true")}
        disabled={disabled}
        options={[
          { value: "true", label: words.yes },
          { value: "false", label: words.no },
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
    return <ObjectEditor label={label} value={value as Record<string, unknown>} onChange={onChange} disabled={disabled} invalidJson={words.invalidJson} />;
  }
  return <Input label={label} value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} disabled={disabled} />;
}

function ObjectEditor({ label, value, onChange, disabled, invalidJson }: { label: string; value: Record<string, unknown>; onChange: (value: Record<string, unknown>) => void; disabled: boolean; invalidJson: string }) {
  const [text, setText] = useState(JSON.stringify(value, null, 2));
  const [invalid, setInvalid] = useState(false);
  return (
    <Textarea
      label={label}
      rows={4}
      value={text}
      disabled={disabled}
      error={invalid ? invalidJson : undefined}
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
  return value.replaceAll("_", " ");
}
