"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
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

function profileSummary(profile: BillingProfile, metrics: Record<BillingMetric, string>, granularities: Record<BillingGranularity, string>, emptyLabel: string, excludeLabel: (types: string) => string) {
  const exclusions = profile.exclude_record_types.length
    ? excludeLabel(profile.exclude_record_types.join(", "))
     : emptyLabel;
  return `${granularities[profile.granularity]} · ${metrics[profile.metric]} · ${exclusions}`;
}

export default function BillingProfilesPage() {
  const t = useTranslations("settings.billingProfiles");
  const metricLabels: Record<BillingMetric, string> = { AMORTIZED_COST: t("metrics.amortized"), NET_AMORTIZED_COST: t("metrics.netAmortized"), UNBLENDED_COST: t("metrics.unblended") };
  const granularityLabels: Record<BillingGranularity, string> = { DAILY: t("granularity.daily"), MONTHLY: t("granularity.monthly") };
  const groupingLabels: Record<BillingGroupBy, string> = { NONE: t("grouping.none"), SERVICE: t("grouping.service"), ACCOUNT: t("grouping.account") };
  const [profiles, setProfiles] = useState<BillingProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState<{kind: "updated" | "created" | "default" | "deactivated"; name: string} | null>(null);
  const [form, setForm] = useState<FormState | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setProfiles(await listBillingProfiles());
    } catch (err) {
      setError(message(err, "ERR_BILLING_PROFILES_LOAD"));
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
    setSuccess(null);
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
        setSuccess({kind: "updated", name: payload.name});
      } else {
        await createBillingProfile(payload);
        setSuccess({kind: "created", name: payload.name});
      }
      setForm(null);
      await load();
    } catch (err) {
      setError(message(err, "ERR_BILLING_PROFILES_SAVE"));
    } finally {
      setSaving(false);
    }
  }

  async function setDefault(profile: BillingProfile) {
    setError("");
    setSuccess(null);
    try {
      await setDefaultBillingProfile(profile.id);
      setSuccess({kind: "default", name: profile.name});
      await load();
    } catch (err) {
      setError(message(err, "ERR_BILLING_PROFILES_DEFAULT"));
    }
  }

  async function deactivate(profile: BillingProfile) {
    setError("");
    setSuccess(null);
    try {
      await deactivateBillingProfile(profile.id);
      setSuccess({kind: "deactivated", name: profile.name});
      await load();
    } catch (err) {
      setError(message(err, "ERR_BILLING_PROFILES_DEACTIVATE"));
    }
  }

  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description")}
        actions={<Button onClick={() => setForm({ ...emptyForm })}>{t("newProfile")}</Button>}
      />

      {error && <Alert variant="danger" title={t("errorTitle")} description={error === "ERR_BILLING_PROFILES_LOAD" ? t("errors.load") : error === "ERR_BILLING_PROFILES_SAVE" ? t("errors.save") : error === "ERR_BILLING_PROFILES_DEFAULT" ? t("errors.setDefault") : error === "ERR_BILLING_PROFILES_DEACTIVATE" ? t("errors.deactivate") : error} />}
      {success && <Alert variant="success" title={t("successTitle")} description={success.kind === "updated" ? t("success.updated", {name: success.name}) : success.kind === "created" ? t("success.created", {name: success.name}) : success.kind === "default" ? t("success.default", {name: success.name}) : t("success.deactivated", {name: success.name})} />}

      {form && (
        <Section
          appearance="card"
          title={form.id ? t("editProfile") : t("newProfile")}
          description={t("saveNote")}
        >
          <form onSubmit={submit} className={styles.formStack}>
            <div className={styles.formGrid}>
              <Input
                label={t("name")}
                required
                maxLength={120}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
              />
              <Input
                label={t("descriptionLabel")}
                maxLength={1000}
                value={form.description ?? ""}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
              />
              <Select
                label={t("metric")}
                value={form.metric}
                onChange={(event) => setForm({ ...form, metric: event.target.value as BillingMetric })}
                options={Object.entries(metricLabels).map(([value, label]) => ({ value, label }))}
              />
              <Select
                label={t("granularityLabel")}
                value={form.granularity}
                onChange={(event) => setForm({ ...form, granularity: event.target.value as BillingGranularity })}
                options={Object.entries(granularityLabels).map(([value, label]) => ({ value, label }))}
              />
              <Select
                label={t("defaultGrouping")}
                value={form.group_by}
                onChange={(event) => setForm({ ...form, group_by: event.target.value as BillingGroupBy })}
                options={Object.entries(groupingLabels).map(([value, label]) => ({ value, label }))}
              />
              {!form.id && (
                <Checkbox
                  label={t("setDefault")}
                  checked={Boolean(form.is_default)}
                  onChange={(event) => setForm({ ...form, is_default: event.target.checked })}
                />
              )}
            </div>

            <fieldset className={styles.formStack}>
              <legend>{t("excludeRecordTypes")}</legend>
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
              <Button type="submit" loading={saving}>{t("save")}</Button>
              <Button variant="ghost" onClick={() => setForm(null)} disabled={saving}>{t("cancel")}</Button>
            </div>
          </form>
        </Section>
      )}

      <Section title={t("availableTitle")} description={t("availableDescription")}>
        <Table aria-label={t("tableLabel")}>
          <TableHeader>
            <TableRow staticRow>
              <TableHead>{t("column.profile")}</TableHead>
              <TableHead>{t("column.config")}</TableHead>
              <TableHead>{t("column.grouping")}</TableHead>
              <TableHead>{t("column.status")}</TableHead>
              <TableHead>{t("column.actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow staticRow>
                <TableState state="loading" colSpan={5}>{t("loading")}</TableState>
              </TableRow>
            ) : profiles.length === 0 ? (
              <TableRow staticRow>
                <TableState state="empty" colSpan={5}>{t("empty")}</TableState>
              </TableRow>
            ) : profiles.map((profile) => (
              <TableRow key={profile.id}>
                <TableCell>
                  <div className={styles.stack}>
                    <div className={styles.inlineMeta}>
                      <strong>{profile.name}</strong>
                      {profile.is_default && <Badge variant="info" appearance="subtle">{t("default")}</Badge>}
                    </div>
                    <span className={styles.secondaryText}>
                      {profile.description || (profile.is_system ? t("systemProfile") : t("noDescription"))}
                    </span>
                  </div>
                </TableCell>
                <TableCell>{profileSummary(profile, metricLabels, granularityLabels, t("noExclusions"), (types) => t("excludes", {types}))}</TableCell>
                <TableCell>{groupingLabels[profile.group_by]}</TableCell>
                <TableCell>
                  <StatusIndicator
                    status={profile.enabled ? "success" : "neutral"}
                    label={profile.enabled ? t("active") : t("inactive")}
                  />
                </TableCell>
                <TableCell>
                  <div className={styles.formActions}>
                    <Button size="sm" variant="ghost" onClick={() => edit(profile)} disabled={!profile.enabled}>
                      {t("edit")}
                    </Button>
                    {!profile.is_default && profile.enabled && (
                      <Button size="sm" variant="outline" onClick={() => void setDefault(profile)}>
                        {t("setDefault")}
                      </Button>
                    )}
                    {!profile.is_default && !profile.is_system && profile.enabled && (
                      <Button size="sm" variant="danger" onClick={() => void deactivate(profile)}>
                        {t("deactivate")}
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
