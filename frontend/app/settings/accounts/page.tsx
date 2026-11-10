"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import {useLocale, useTranslations} from "next-intl";
import {
  Building2,
  Check,
  Copy,
  Edit3,
  FileKey2,
  Play,
  Plus,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { CollectionScheduleFields } from "@/components/collection-schedule-fields";
import { PageHeader } from "@/components/page-header";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, api, formatDate } from "@/lib/api";
import {
  accountToForm,
  buildCreateAccountPayload,
  buildUpdateAccountPayload,
  createEmptyAccountForm,
  filterCloudAccounts,
  validateAccountForm,
} from "@/lib/account-form.mjs";
import type { AccountFormState } from "@/lib/account-form.mjs";
import { scheduleSummary } from "@/lib/account-scheduling.mjs";
import { providerLabel } from "@/lib/cloud.mjs";
import { queryKeys } from "@/lib/query-keys.mjs";
import { invalidateApiQueries } from "@/lib/server-state";
import {
  canManageCloudAccounts,
  canRunCloudAnalysis,
} from "@/lib/settings-navigation.mjs";
import type { CloudAccount, ProviderCapabilities, Scan } from "@/lib/types";

type CurrentUser = { role: string };
type FormMode = "closed" | "create" | "edit";
type ConnectionResult = {
  ok: boolean;
  provider: string;
  error_code?: string | null;
  error?: string | null;
  verified_checks?: string[];
};

function errorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.code) {
    return error.message + " (" + error.code + ")";
  }
  return error instanceof Error ? error.message : fallback;
}

function scopeSummary(account: CloudAccount, labels: { noRegions: string; unavailable: string; root: string; count: (count: number) => string; subcompartments: string; empty: string }) {
  if (account.aws_configuration) {
    return account.aws_configuration.regions.length
      ? account.aws_configuration.regions.join(", ")
      : labels.noRegions;
  }
  const oci = account.oci_configuration;
  if (!oci) return labels.unavailable;
  const parts: string[] = [];
  if (oci.scope_regions.length) parts.push(oci.scope_regions.join(", "));
  if (oci.include_root_compartment) parts.push(labels.root);
  if (oci.compartment_ocids.length) parts.push(labels.count(oci.compartment_ocids.length));
  if (oci.include_subcompartments) parts.push(labels.subcompartments);
  return parts.length ? parts.join(" · ") : labels.empty;
}

export default function AccountsPage() {
  const locale = useLocale();
  const t = useTranslations("settings.accounts");
  const [accounts, setAccounts] = useState<CloudAccount[]>([]);
  const [capabilities, setCapabilities] = useState<ProviderCapabilities[]>([]);
  const [role, setRole] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [mode, setMode] = useState<FormMode>("closed");
  const [editingAccount, setEditingAccount] = useState<CloudAccount | null>(null);
  const [form, setForm] = useState<AccountFormState>(() => createEmptyAccountForm());
  const [replaceCredentials, setReplaceCredentials] = useState(false);
  const [formBusy, setFormBusy] = useState(false);
  const [externalIdBusy, setExternalIdBusy] = useState(false);
  const [busyAccounts, setBusyAccounts] = useState<Record<number, string>>({});
  const [cloudFilter, setCloudFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const canManageAccounts = canManageCloudAccounts(role);
  const canAnalyze = canRunCloudAnalysis(role);
  const capabilityByProvider = useMemo(
    () => new Map(capabilities.map((item) => [item.provider, item])),
    [capabilities],
  );
  const availableProviders = useMemo(
    () => capabilities.filter((item) => item.registration),
    [capabilities],
  );
  const filteredAccounts = useMemo(
    () => filterCloudAccounts(accounts, cloudFilter, search),
    [accounts, cloudFilter, search],
  );

  const dirty = useMemo(() => {
    if (mode === "create") {
      return Boolean(
        form.provider
        || form.name
        || form.native_account_id
        || form.oci.private_key_pem
        || form.oci.private_key_password,
      );
    }
    if (mode === "edit" && editingAccount) {
      return Object.keys(
        buildUpdateAccountPayload(editingAccount, form, { replaceCredentials }),
      ).length > 0;
    }
    return false;
  }, [editingAccount, form, mode, replaceCredentials]);

  async function loadAccounts() {
    try {
      const items = await api<CloudAccount[]>("/cloud-accounts");
      setAccounts(items);
      setLoadError("");
      return true;
    } catch (err) {
      const message = errorMessage(err, t("errorLoad"));
      setLoadError(message);
      setError(message);
      return false;
    }
  }

  useEffect(() => {
    let active = true;
    Promise.all([
      api<CloudAccount[]>("/cloud-accounts"),
      api<ProviderCapabilities[]>("/cloud-accounts/capabilities"),
      api<CurrentUser>("/auth/me"),
    ])
      .then(([items, providerCapabilities, user]) => {
        if (!active) return;
        setAccounts(items);
        setCapabilities(providerCapabilities);
        setRole(user.role);
        setLoadError("");
      })
      .catch((err) => {
        if (!active) return;
        const message = errorMessage(err, t("errorLoad"));
        setError(message);
        setLoadError(message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function setAccountBusy(accountId: number, action: string | null) {
    setBusyAccounts((current) => {
      const next = { ...current };
      if (action) next[accountId] = action;
      else delete next[accountId];
      return next;
    });
  }

  function resetEditor() {
    setMode("closed");
    setEditingAccount(null);
    setReplaceCredentials(false);
    setFieldErrors({});
    setForm(createEmptyAccountForm());
  }

  function closeEditor() {
    if (dirty && !window.confirm(t("discard"))) return;
    resetEditor();
    setError("");
  }

  function openCreate() {
    if (!canManageAccounts) return;
    setMessage("");
    setError("");
    setEditingAccount(null);
    setReplaceCredentials(false);
    setFieldErrors({});
    setForm(createEmptyAccountForm());
    setMode("create");
  }

  async function generateExternalId() {
    setExternalIdBusy(true);
    setError("");
    try {
      const generated = await api<{ external_id: string }>("/cloud-accounts/aws/external-id");
      setForm((current) => current.provider === "aws"
        ? { ...current, aws: { ...current.aws, external_id: generated.external_id } }
        : current);
    } catch (err) {
      setError(errorMessage(err, t("errorExternal")));
    } finally {
      setExternalIdBusy(false);
    }
  }

  async function chooseProvider(provider: string) {
    if (provider !== "aws" && provider !== "oci") {
      setError(t("notImplemented", {provider: providerLabel(provider)}));
      return;
    }
    const next = createEmptyAccountForm(provider);
    next.name = form.name;
    next.enabled = form.enabled;
    setReplaceCredentials(false);
    setFieldErrors({});
    setForm(next);
    if (provider === "aws") await generateExternalId();
  }

  async function openEdit(account: CloudAccount) {
    if (!canManageAccounts) return;
    if (dirty && !window.confirm(t("discardEdit"))) return;
    setFormBusy(true);
    setError("");
    setMessage("");
    try {
      const details = await api<CloudAccount>("/cloud-accounts/" + account.id);
      setEditingAccount(details);
      setForm(accountToForm(details));
      setReplaceCredentials(false);
      setFieldErrors({});
      setMode("edit");
    } catch (err) {
      setError(errorMessage(err, t("errorAccount")));
    } finally {
      setFormBusy(false);
    }
  }

  async function readPemFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 65536) {
      setFieldErrors((current) => ({
        ...current,
        private_key_pem: t("largeKey"),
      }));
      setError(t("largeKey"));
      return;
    }
    const pem = await file.text();
    setForm((current) => ({
      ...current,
      oci: { ...current.oci, private_key_pem: pem },
    }));
    setFieldErrors((current) => {
      const next = { ...current };
      delete next.private_key_pem;
      return next;
    });
    setError("");
  }

  function cancelCredentialReplacement() {
    setReplaceCredentials(false);
    setForm((current) => ({
      ...current,
      oci: {
        ...current.oci,
        fingerprint: editingAccount?.oci_configuration?.fingerprint || current.oci.fingerprint,
        private_key_pem: "",
        private_key_password: "",
      },
    }));
  }

  async function submitForm(event: FormEvent) {
    event.preventDefault();
    if (!canManageAccounts) return;
    const validation = validateAccountForm(form, {
      mode: mode === "edit" ? "edit" : "create",
      replaceCredentials,
      messages: {
        name: t("validation.name"),
        provider: t("validation.provider"),
        interval: t("validation.interval"),
        awsId: t("validation.awsId"),
        roleArn: t("validation.roleArn"),
        roleAccount: t("validation.roleAccount"),
        externalId: t("validation.externalId"),
        regions: t("validation.regions"),
        tenancy: t("validation.tenancy"),
        userOcid: t("validation.userOcid"),
        connectionRegion: t("validation.connectionRegion"),
        compartment: t("validation.compartment"),
        fingerprint: t("validation.fingerprint"),
        pem: t("validation.pem"),
      },
    });
    setFieldErrors(validation);
    if (Object.keys(validation).length) {
      setError(t("checkFields"));
      return;
    }
    setFormBusy(true);
    setError("");
    setMessage("");
    try {
      if (mode === "create") {
        const payload = buildCreateAccountPayload(form);
        const created = await api<CloudAccount>("/cloud-accounts", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        resetEditor();
        setMessage(
          created.provider === "oci"
            ? t("createdOci")
            : t("createdAws"),
        );
      } else if (mode === "edit" && editingAccount) {
        const payload = buildUpdateAccountPayload(editingAccount, form, { replaceCredentials });
        if (!Object.keys(payload).length) {
          setMessage(t("noChanges"));
          setFormBusy(false);
          return;
        }
        const saved = await api<CloudAccount>("/cloud-accounts/" + editingAccount.id, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        resetEditor();
        setMessage(
          replaceCredentials
            ? t("credentialsReplaced")
            : saved.connection_status === "untested"
              ? t("savedRetest")
              : t("saved"),
        );
      }
      invalidateApiQueries(queryKeys.dashboard.all);
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.collections.all);
      await loadAccounts();
    } catch (err) {
      setError(errorMessage(err, t("errorSave")));
    } finally {
      setFormBusy(false);
    }
  }

  async function testConnection(account: CloudAccount) {
    if (!canManageAccounts) return;
    if (mode === "edit" && editingAccount?.id === account.id && dirty) {
      setError(t("saveBeforeTest"));
      return;
    }
    setAccountBusy(account.id, "test");
    setError("");
    setMessage("");
    try {
      const result = await api<ConnectionResult>(
        "/cloud-accounts/" + account.id + "/test-connection",
        { method: "POST" },
      );
      if (!result.ok) {
        const suffix = result.error_code ? " (" + result.error_code + ")" : "";
        throw new Error((result.error || t("connectionInvalid")) + suffix);
      }
      const checks = result.verified_checks?.length
        ? t("verifiedChecks", {checks: result.verified_checks.join(", ")})
        : "";
      setMessage(t("connectionValidated", {name:account.name}) + checks);
      await loadAccounts();
    } catch (err) {
      setError(errorMessage(err, t("errorConnection")));
      await loadAccounts();
    } finally {
      setAccountBusy(account.id, null);
    }
  }

  async function scan(account: CloudAccount) {
    if (!canAnalyze) return;
    const capability = capabilityByProvider.get(account.provider);
    if (!capability?.manual_collection) {
      setError(t("notCollectable", {provider:providerLabel(account.provider)}));
      return;
    }
    setAccountBusy(account.id, "scan");
    setError("");
    setMessage("");
    try {
      await api<Scan>("/cloud-accounts/" + account.id + "/scans", {
        method: "POST",
      });
      invalidateApiQueries(queryKeys.dashboard.all);
      invalidateApiQueries(queryKeys.collections.all);
      setMessage(t("queued", {name:account.name}));
    } catch (err) {
      setError(errorMessage(err, t("errorScan")));
    } finally {
      setAccountBusy(account.id, null);
    }
  }

  async function copyText(value: string, label: string) {
    try {
      await navigator.clipboard.writeText(value);
      setMessage(t("copied", {label}));
      setError("");
    } catch {
      setError(t("copyFailed"));
    }
  }

  const editorTitle = mode === "create" ? t("add") : t("accountEdited", {name: editingAccount?.name || t("accountGeneric")});
  const formCapability = form.provider ? capabilityByProvider.get(form.provider) : undefined;

  return (
    <>
      <PageHeader
        eyebrow={t("eyebrow")}
        title={t("title")}
        description={t("description")}
        actions={canManageAccounts ? (
          <button className="button primary" onClick={openCreate} disabled={mode !== "closed"}>
            <Plus size={17} /> {t("add")}
          </button>
        ) : undefined}
      />

      <div aria-live="polite">
        {error && <div className="alert error"><X size={17} />{error}</div>}
        {message && <div className="alert success"><Check size={17} />{message}</div>}
      </div>

      {mode !== "closed" && canManageAccounts && (
        <section className="panel account-form-panel" aria-labelledby="account-editor-title">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">{mode === "create" ? t("newConnection") : t("maintenance")}</span>
              <h2 id="account-editor-title">{editorTitle}</h2>
            </div>
            <button className="icon-button" type="button" aria-label={t("closedForm")} onClick={closeEditor}>
              <X size={18} />
            </button>
          </div>

          <form className="form-grid account-unified-form" onSubmit={submitForm}>
            {mode === "create" && (
              <fieldset className="span-2 account-provider-fieldset">
                <legend>{t("cloud")}</legend>
                <div className="segmented account-provider-choice" aria-label={t("chooseProvider")}>
                  {availableProviders.map((provider) => (
                    <button
                      key={provider.provider}
                      type="button"
                      className={form.provider === provider.provider ? "active" : ""}
                      aria-pressed={form.provider === provider.provider}
                      onClick={() => void chooseProvider(provider.provider)}
                    >
                      {provider.label}
                    </button>
                  ))}
                </div>
                <small>{t("providerNote")}</small>
                {fieldErrors.provider && <span className="field-error">{fieldErrors.provider}</span>}
              </fieldset>
            )}

            {form.provider && (
              <>
                <label>
                  {t("accountName")}
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    placeholder={t("production")}
                    required
                    disabled={formBusy}
                  />
                  {fieldErrors.name && <span className="field-error">{fieldErrors.name}</span>}
                </label>
                <label>
                  {form.provider === "aws" ? "AWS Account ID" : "Tenancy OCID"}
                  <input
                    value={form.native_account_id}
                    onChange={(e) => setForm({
                      ...form,
                      native_account_id: form.provider === "aws"
                        ? e.target.value.replace(/\D/g, "").slice(0, 12)
                        : e.target.value,
                    })}
                    placeholder={form.provider === "aws" ? "123456789012" : "ocid1.tenancy.oc1.."}
                    pattern={form.provider === "aws" ? "[0-9]{12}" : undefined}
                    readOnly={mode === "edit"}
                    required
                    disabled={formBusy}
                  />
                  {fieldErrors.native_account_id && <span className="field-error">{fieldErrors.native_account_id}</span>}
                  {mode === "edit" && (
                    <small>{t("identityNote")}</small>
                  )}
                </label>

                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={form.enabled}
                    onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
                    disabled={formBusy}
                  />
                  {t("enabled")}
                </label>
                <div />

                {form.provider === "aws" && (
                  <>
                    <label className="span-2">
                      Role ARN
                      <input
                        value={form.aws.role_arn}
                        onChange={(e) => setForm({
                          ...form,
                          aws: { ...form.aws, role_arn: e.target.value },
                        })}
                        placeholder="arn:aws:iam::123456789012:role/FinOpsReadOnly"
                        required
                        disabled={formBusy}
                      />
                      {fieldErrors.role_arn && <span className="field-error">{fieldErrors.role_arn}</span>}
                    </label>
                    <label className="span-2">
                      External ID
                      <div className="input-action">
                        <input
                          value={form.aws.external_id}
                          onChange={(e) => setForm({
                            ...form,
                            aws: { ...form.aws, external_id: e.target.value },
                          })}
                          required
                          disabled={formBusy}
                        />
                        <button
                          type="button"
                          title={t("copyExternal")}
                          aria-label={t("copyExternal")}
                          onClick={() => void copyText(form.aws.external_id, "External ID")}
                          disabled={formBusy}
                        >
                          <Copy size={16} />
                        </button>
                      </div>
                      {fieldErrors.external_id && <span className="field-error">{fieldErrors.external_id}</span>}
                      <small>
                        {mode === "create" ? t("newExternal") : t("existingExternal")}
                      </small>
                    </label>
                    {mode === "create" && (
                      <div className="span-2 account-inline-actions">
                        <button
                          type="button"
                          className="button ghost"
                          onClick={() => void generateExternalId()}
                          disabled={externalIdBusy || formBusy}
                        >
                          <RefreshCw size={15} className={externalIdBusy ? "spin" : ""} />
                          {externalIdBusy ? t("generating") : t("generateExternal")}
                        </button>
                      </div>
                    )}
                    <label>
                      {t("regions")}
                      <input
                        value={form.aws.regions}
                        onChange={(e) => setForm({
                          ...form,
                          aws: { ...form.aws, regions: e.target.value },
                        })}
                        placeholder="sa-east-1, us-east-1"
                        required
                        disabled={formBusy}
                      />
                      {fieldErrors.regions && <span className="field-error">{fieldErrors.regions}</span>}
                      <small>{t("commaSeparated")}</small>
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={form.aws.is_management_account}
                        onChange={(e) => setForm({
                          ...form,
                          aws: { ...form.aws, is_management_account: e.target.checked },
                        })}
                        disabled={formBusy}
                      />
                      {t("payer")}
                    </label>
                    <p className="span-2 account-form-note">
                      {t("roleWarning")}
                    </p>
                  </>
                )}

                {form.provider === "oci" && (
                  <>
                    <label className="span-2">
                      User OCID
                      <input
                        value={form.oci.user_ocid}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, user_ocid: e.target.value },
                        })}
                        placeholder="ocid1.user.oc1.."
                        required
                        disabled={formBusy}
                      />
                      {fieldErrors.user_ocid && <span className="field-error">{fieldErrors.user_ocid}</span>}
                    </label>
                    <label>
                      {t("connectionRegion")}
                      <input
                        value={form.oci.region}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, region: e.target.value },
                        })}
                        placeholder="sa-saopaulo-1"
                        required
                        disabled={formBusy}
                      />
                      {fieldErrors.region && <span className="field-error">{fieldErrors.region}</span>}
                      <small>{t("regionNote")}</small>
                    </label>
                    <label>
                      {t("scopeRegions")}
                      <input
                        value={form.oci.scope_regions}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, scope_regions: e.target.value },
                        })}
                        placeholder="sa-saopaulo-1, us-ashburn-1"
                        disabled={formBusy}
                      />
                      <small>{t("scopeNote")}</small>
                    </label>
                    <label className="span-2">
                      {t("compartments")}
                      <textarea
                        value={form.oci.compartment_ocids}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, compartment_ocids: e.target.value },
                        })}
                        placeholder="ocid1.compartment.oc1..abc, ocid1.compartment.oc1..def"
                        rows={3}
                        disabled={formBusy}
                      />
                      {fieldErrors.compartment_ocids && <span className="field-error">{fieldErrors.compartment_ocids}</span>}
                      <small>{t("ocidsNote")}</small>
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={form.oci.include_root_compartment}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, include_root_compartment: e.target.checked },
                        })}
                        disabled={formBusy}
                      />
                      {t("rootCompartment")}
                    </label>
                    <label className="check-label">
                      <input
                        type="checkbox"
                        checked={form.oci.include_subcompartments}
                        onChange={(e) => setForm({
                          ...form,
                          oci: { ...form.oci, include_subcompartments: e.target.checked },
                        })}
                        disabled={formBusy}
                      />
                      {t("subcompartments")}
                    </label>

                    {mode === "create" ? (
                      <>
                        <label>
                          Fingerprint
                          <input
                            value={form.oci.fingerprint}
                            onChange={(e) => setForm({
                              ...form,
                              oci: { ...form.oci, fingerprint: e.target.value },
                            })}
                            placeholder="aa:bb:cc:..."
                            required
                            disabled={formBusy}
                          />
                          {fieldErrors.fingerprint && <span className="field-error">{fieldErrors.fingerprint}</span>}
                        </label>
                        <label>
                          {t("passphrase")}
                          <input
                            type="password"
                            autoComplete="new-password"
                            value={form.oci.private_key_password}
                            onChange={(e) => setForm({
                              ...form,
                              oci: { ...form.oci, private_key_password: e.target.value },
                            })}
                            placeholder={t("optional")}
                            disabled={formBusy}
                          />
                        </label>
                        <OciPrivateKeyFields
                          form={form}
                          setForm={setForm}
                          readPemFile={readPemFile}
                          error={fieldErrors.private_key_pem}
                          disabled={formBusy}
                        />
                      </>
                    ) : (
                      <>
                        <div className="span-2 credential-summary">
                          <div>
                            <FileKey2 size={18} />
                            <div>
                              <strong>
                                {editingAccount?.oci_configuration?.credentials_configured ? t("credentialsConfigured") : t("credentialsMissing")}
                              </strong>
                              <span>
                                {t("credentialsWarning")}
                              </span>
                            </div>
                          </div>
                          {!replaceCredentials ? (
                            <button
                              type="button"
                              className="button ghost"
                              disabled={formBusy}
                              onClick={() => {
                                setReplaceCredentials(true);
                                setForm((current) => ({
                                  ...current,
                                  oci: { ...current.oci, private_key_pem: "", private_key_password: "" },
                                }));
                              }}
                            >
                              {t("replaceCredentials")}
                            </button>
                          ) : (
                            <button type="button" className="button ghost" onClick={cancelCredentialReplacement} disabled={formBusy}>
                              {t("cancelReplacement")}
                            </button>
                          )}
                        </div>
                        {!replaceCredentials && (
                          <label className="span-2">
                            {t("currentFingerprint")}
                            <input value={form.oci.fingerprint} readOnly />
                          </label>
                        )}
                        {replaceCredentials && (
                          <>
                            <label>
                              {t("newFingerprint")}
                              <input
                                value={form.oci.fingerprint}
                                onChange={(e) => setForm({
                                  ...form,
                                  oci: { ...form.oci, fingerprint: e.target.value },
                                })}
                                placeholder="aa:bb:cc:..."
                                required
                                disabled={formBusy}
                              />
                              {fieldErrors.fingerprint && <span className="field-error">{fieldErrors.fingerprint}</span>}
                            </label>
                            <label>
                              {t("newPassphrase")}
                              <input
                                type="password"
                                autoComplete="new-password"
                                value={form.oci.private_key_password}
                                onChange={(e) => setForm({
                                  ...form,
                                  oci: { ...form.oci, private_key_password: e.target.value },
                                })}
                                placeholder={t("optional")}
                                disabled={formBusy}
                              />
                            </label>
                            <OciPrivateKeyFields
                              form={form}
                              setForm={setForm}
                              readPemFile={readPemFile}
                              error={fieldErrors.private_key_pem}
                              disabled={formBusy}
                            />
                            <p className="span-2 account-form-note">
                              {t("replacementNote")}
                            </p>
                          </>
                        )}
                      </>
                    )}
                    {!formCapability?.manual_collection && (
                      <p className="span-2 account-form-note">
                        {t("manualUnavailable")}
                      </p>
                    )}
                  </>
                )}

                <CollectionScheduleFields
                  supported={formCapability?.scheduling === true}
                  scheduleEnabled={form.schedule_enabled}
                  scanIntervalHours={form.scan_interval_hours}
                  nextScanAt={mode === "edit" ? editingAccount?.next_scan_at : null}
                  showNextScan={mode === "edit"}
                  disabled={formBusy}
                  error={fieldErrors.scan_interval_hours}
                  onScheduleEnabledChange={(scheduleEnabled) => setForm((current) => ({
                    ...current,
                    schedule_enabled: scheduleEnabled,
                  }))}
                  onIntervalChange={(scanIntervalHours) => setForm((current) => ({
                    ...current,
                    scan_interval_hours: scanIntervalHours,
                  }))}
                />

                <div className="form-actions span-2">
                  <button type="button" className="button ghost" onClick={closeEditor} disabled={formBusy}>
                    {t("cancel")}
                  </button>
                  <button className="button primary" disabled={formBusy || !form.provider}>
                    {formBusy ? t("saving") : mode === "create" ? t("create") : t("save")}
                  </button>
                </div>
              </>
            )}
          </form>
        </section>
      )}

      <section className="panel table-panel accounts-table-panel">
        <div className="toolbar accounts-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("search")}
              aria-label={t("search")}
            />
          </label>
          <label className="select-field">
            {t("cloud")}
            <select value={cloudFilter} onChange={(e) => setCloudFilter(e.target.value)} aria-label={t("cloud")}>
              <option value="all">{t("all")}</option>
              {availableProviders.map((provider) => (
                <option key={provider.provider} value={provider.provider}>{provider.label}</option>
              ))}
            </select>
          </label>
        </div>

        {loading ? (
          <div className="empty-state account-list-state">
            <RefreshCw size={24} className="spin" />
            <strong>{t("loading")}</strong>
            <p>{t("registry")}</p>
          </div>
        ) : loadError && accounts.length === 0 ? (
          <div className="empty-state account-list-state">
            <X size={24} />
            <strong>{t("loadingError")}</strong>
            <p>{loadError}</p>
            <button className="button ghost" onClick={() => void loadAccounts()}>
              <RefreshCw size={16} /> {t("retry")}
            </button>
          </div>
        ) : accounts.length === 0 ? (
          <div className="empty-state account-list-state">
            <Building2 size={24} />
            <strong>{t("empty")}</strong>
            <p>{canManageAccounts ? t("emptyAdmin") : t("emptyViewer")}</p>
            {canManageAccounts && <button className="button primary" onClick={openCreate}><Plus size={16} /> {t("add")}</button>}
          </div>
        ) : filteredAccounts.length === 0 ? (
          <div className="empty-state account-list-state">
            <Search size={24} />
            <strong>{t("noResults")}</strong>
            <p>{t("searchHelp")}</p>
          </div>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table settings-table accounts-table">
              <thead>
                <tr>
                  <th>{t("account")}</th>
                  <th>{t("id")}</th>
                  <th>{t("state")}</th>
                  <th>{t("scope")}</th>
                  <th>{t("lastTest")}</th>
                  <th>{t("scheduling")}</th>
                  <th>{t("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filteredAccounts.map((account) => {
                  const busy = busyAccounts[account.id];
                  const capability = capabilityByProvider.get(account.provider);
                  return (
                    <tr key={account.id}>
                      <td>
                        <strong>{account.name}</strong>
                        <span>{account.enabled ? t("enabledStatus") : t("disabledStatus")}</span>
                      </td>
                      <td>
                        <strong>{providerLabel(account.provider)}</strong>
                        <div className="account-identifier">
                          <code title={account.native_account_id}>{account.native_account_id}</code>
                          <button
                            type="button"
                            className="icon-button compact"
                            title={t("copyId")}
                            aria-label={t("copyIdFor", {account:account.name})}
                            onClick={() => void copyText(account.native_account_id, "Identificador")}
                          >
                            <Copy size={14} />
                          </button>
                        </div>
                      </td>
                      <td>
                        <StatusBadge value={account.connection_status} />
                        {account.last_error && <span className="account-table-error" title={account.last_error}>{account.last_error}</span>}
                      </td>
                      <td>
                        <span title={scopeSummary(account, {noRegions:t("scopeNoRegions"), unavailable:t("scopeUnavailable"), root:t("scopeRoot"), count:(count)=>t("scopeCompartments", {count}), subcompartments:t("scopeSubcompartments"), empty:t("scopeEmpty")})}>{scopeSummary(account, {noRegions:t("scopeNoRegions"), unavailable:t("scopeUnavailable"), root:t("scopeRoot"), count:(count)=>t("scopeCompartments", {count}), subcompartments:t("scopeSubcompartments"), empty:t("scopeEmpty")})}</span>
                        {capability && !capability.manual_collection && (
                          <small className="account-capability-note">
                            {account.connection_status === "connected"
                              ? t("connectedCollection", {provider:capability.label})
                              : t("disabledCollection", {provider:capability.label})}
                          </small>
                        )}
                      </td>
                      <td>{formatDate(account.last_connection_test_at, locale)}</td>
                      <td>{!capability?.scheduling ? t("scheduleUnsupported") : !account.schedule_enabled ? t("scheduleDisabled") : account.scan_interval_hours === 12 ? t("schedule12") : account.scan_interval_hours === 24 ? t("schedule24") : account.scan_interval_hours === 168 ? t("schedule168") : scheduleSummary(account, capability)}</td>
                      <td>
                        <div className="settings-row-actions account-row-actions">
                          {canManageAccounts && (
                            <button
                              className="button ghost"
                              onClick={() => void openEdit(account)}
                              disabled={Boolean(busy) || formBusy}
                            >
                              <Edit3 size={15} /> {t("edit")}
                            </button>
                          )}
                          {canManageAccounts && capability?.connection_test && (
                            <button
                              className="button ghost"
                              onClick={() => void testConnection(account)}
                              disabled={Boolean(busy)}
                            >
                              <RefreshCw size={15} className={busy === "test" ? "spin" : ""} />
                              {t("test")}
                            </button>
                          )}
                          {canAnalyze && capability?.manual_collection && (
                            <button
                              className="button primary"
                              onClick={() => void scan(account)}
                              disabled={
                                Boolean(busy)
                                || !account.enabled
                                || account.connection_status !== "connected"
                              }
                            >
                              <Play size={15} /> {t("analyze")}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function OciPrivateKeyFields({
  form,
  setForm,
  readPemFile,
  error,
  disabled = false,
}: {
  form: AccountFormState;
  setForm: (value: AccountFormState | ((current: AccountFormState) => AccountFormState)) => void;
  readPemFile: (event: ChangeEvent<HTMLInputElement>) => Promise<void>;
  error?: string;
  disabled?: boolean;
}) {
  const t = useTranslations("settings.accounts");
  return (
    <>
      <label className="span-2">
        {t("pemFile")}
        <input
          type="file"
          accept=".pem,.key,text/plain,application/x-pem-file"
          onChange={(event) => void readPemFile(event)}
          disabled={disabled}
        />
        <small>{t("pemNote")}</small>
      </label>
      <label className="span-2">
        {t("pemKey")}
        <textarea
          value={form.oci.private_key_pem}
          onChange={(e) => setForm({
            ...form,
            oci: { ...form.oci, private_key_pem: e.target.value },
          })}
          placeholder="-----BEGIN PRIVATE KEY-----"
          rows={7}
          required
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
        />
        {error && <span className="field-error">{error}</span>}
        <small>{t("pemAlternate")}</small>
      </label>
    </>
  );
}
