"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { AlertTriangle, Eye, Save } from "lucide-react";
import { PageHeader, Section } from "@/components/aven";
import { Alert, Button, Card, Input, Select, Switch } from "@/components/ui";
import { api, ApiError, formatDate } from "@/lib/api";
import { iconDefaults } from "@/lib/iconography";
import styles from "./page.module.css";

type CycleMode = "CALENDAR_MONTH" | "FIXED_DAYS";

type CycleSummary = {
  id: string;
  label: string;
  period_start: string;
  period_end: string;
  status: string;
  timezone: string;
  policy_version: number | null;
};

type Maintenance = {
  last_retention_run_at: string | null;
  last_cycle_close_check_at: string | null;
  last_observation_cleanup_at: string | null;
};

type OpportunityPolicy = {
  id: string;
  cycle_mode: CycleMode;
  cycle_length_days: number;
  cycle_timezone: string;
  cycle_anchor_date: string | null;
  automatic_cycle_close_enabled: boolean;
  treated_archive_enabled: boolean;
  treated_archive_days: number;
  rejected_archive_enabled: boolean;
  rejected_archive_days: number;
  resolved_external_archive_enabled: boolean;
  resolved_external_archive_days: number;
  open_archive_enabled: boolean;
  open_archive_days: number;
  observation_retention_days: number;
  enabled: boolean;
  version: number;
  updated_at: string;
  updated_by: string | null;
  current_cycle: CycleSummary | null;
  next_cycle_start: string | null;
  maintenance: Maintenance;
};

type Preview = {
  treated_eligible: number;
  rejected_eligible: number;
  resolved_externally_eligible: number;
  open_eligible: number;
  observations_eligible_for_purge: number;
  overdue_cycles_awaiting_close: number;
  current_cycle: CycleSummary | null;
  warnings: string[];
};

function editable(policy: OpportunityPolicy) {
  return {
    cycle_mode: policy.cycle_mode,
    cycle_length_days: policy.cycle_length_days,
    cycle_timezone: policy.cycle_timezone,
    cycle_anchor_date: policy.cycle_anchor_date,
    automatic_cycle_close_enabled: policy.automatic_cycle_close_enabled,
    treated_archive_enabled: policy.treated_archive_enabled,
    treated_archive_days: policy.treated_archive_days,
    rejected_archive_enabled: policy.rejected_archive_enabled,
    rejected_archive_days: policy.rejected_archive_days,
    resolved_external_archive_enabled: policy.resolved_external_archive_enabled,
    resolved_external_archive_days: policy.resolved_external_archive_days,
    open_archive_enabled: policy.open_archive_enabled,
    open_archive_days: policy.open_archive_days,
    observation_retention_days: policy.observation_retention_days,
    enabled: policy.enabled,
  };
}

export default function OpportunityPolicyPage() {
  const t = useTranslations("settings.opportunities");
  const [policy, setPolicy] = useState<OpportunityPolicy | null>(null);
  const [initial, setInitial] = useState<OpportunityPolicy | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let active = true;
    api<OpportunityPolicy>("/settings/opportunity-policy")
      .then((data) => {
        if (!active) return;
        setPolicy(data);
        setInitial(data);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "ERR_OPP_POLICY_LOAD");
      });
    return () => { active = false; };
  }, []);

  const reductionWarning = useMemo(() => {
    if (!policy || !initial) return false;
    return (
      policy.observation_retention_days < initial.observation_retention_days ||
      policy.treated_archive_days < initial.treated_archive_days ||
      policy.rejected_archive_days < initial.rejected_archive_days ||
      policy.resolved_external_archive_days < initial.resolved_external_archive_days ||
      (policy.open_archive_enabled && policy.open_archive_days < initial.open_archive_days)
    );
  }, [policy, initial]);

  function patch(changes: Partial<OpportunityPolicy>) {
    setPolicy((current) => current ? { ...current, ...changes } : current);
    setPreview(null);
    setMessage("");
  }

  async function runPreview() {
    if (!policy) return;
    setBusy(true);
    setError("");
    try {
      setPreview(
        await api<Preview>("/settings/opportunity-policy/preview", {
          method: "POST",
          body: JSON.stringify(editable(policy)),
        }),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "ERR_OPP_POLICY_PREVIEW");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!policy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await api<OpportunityPolicy>("/settings/opportunity-policy", {
        method: "PUT",
        body: JSON.stringify({ ...editable(policy), expected_version: policy.version }),
      });
      setPolicy(saved);
      setInitial(saved);
      setPreview(null);
      setMessage("OPP_POLICY_UPDATED");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError(
          "ERR_OPP_POLICY_CONFLICT",
        );
      } else {
        setError(err instanceof Error ? err.message : "ERR_OPP_POLICY_SAVE");
      }
    } finally {
      setBusy(false);
    }
  }

  if (!policy) {
    return (
      <div className={styles.page}>
        <PageHeader
          title={t("title")}
          description={t("loadingDescription")}
          metadata={<span>{t("metadata")}</span>}
        />
        {error && <Alert variant="danger" title={t("loadErrorTitle")} description={error === "ERR_OPP_POLICY_LOAD" ? t("errors.load") : error === "ERR_OPP_POLICY_PREVIEW" ? t("errors.preview") : error === "ERR_OPP_POLICY_SAVE" ? t("errors.save") : error === "ERR_OPP_POLICY_CONFLICT" ? t("errors.conflict") : error} />}
      </div>
    );
  }

  const cycle = policy.current_cycle;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("title")}
        description={t("description")}
        metadata={<span>{t("metadata")}</span>}
      />

      {error && <Alert variant="danger" title={t("updateErrorTitle")} description={error === "ERR_OPP_POLICY_LOAD" ? t("errors.load") : error === "ERR_OPP_POLICY_PREVIEW" ? t("errors.preview") : error === "ERR_OPP_POLICY_SAVE" ? t("errors.save") : error === "ERR_OPP_POLICY_CONFLICT" ? t("errors.conflict") : error} />}
      {message && <Alert variant="success" title={message === "OPP_POLICY_UPDATED" ? t("updated") : message} />}

      <section className={styles.statusGrid} aria-label={t("summaryAria")}>
        <PolicyStatus label={t("version")} value={String(policy.version)} detail={t("updatedAt", {date: formatDate(policy.updated_at)})} />
        <PolicyStatus
          label={t("currentCycle")}
          value={cycle?.label || t("notCreated")}
          detail={cycle ? `${formatDate(cycle.period_start)} → ${formatDate(cycle.period_end)}` : t("willCreate")}
        />
        <PolicyStatus
          label={t("nextClosure")}
          value={policy.next_cycle_start ? formatDate(policy.next_cycle_start) : "—"}
          detail={policy.automatic_cycle_close_enabled ? t("automatic") : t("manualClosure")}
        />
      </section>

      <Section
        appearance="card"
        title={t("cyclesTitle")}
        description={t("cyclesDescription")}
        actions={(
          <Switch
            aria-label={t("automaticClosureAria")}
            checked={policy.automatic_cycle_close_enabled}
            onCheckedChange={(checked) => patch({ automatic_cycle_close_enabled: checked })}
          />
        )}
      >
        <div className={styles.formGrid}>
          <Select
            label={t("cycleMode")}
            value={policy.cycle_mode}
            onChange={(event) => patch({ cycle_mode: event.target.value as CycleMode })}
            options={[
              { value: "CALENDAR_MONTH", label: t("calendarMonth") },
              { value: "FIXED_DAYS", label: t("fixedDays") },
            ]}
          />
          <Input
            label={t("timezone")}
            value={policy.cycle_timezone}
            list="cycle-timezones"
            onChange={(event) => patch({ cycle_timezone: event.target.value })}
          />
          <datalist id="cycle-timezones">
            <option value="UTC" />
            <option value="America/Sao_Paulo" />
          </datalist>
          {policy.cycle_mode === "FIXED_DAYS" && (
            <>
              <Input
                label={t("cycleLength")}
                type="number"
                min={7}
                max={365}
                value={policy.cycle_length_days}
                onChange={(event) => patch({ cycle_length_days: Number(event.target.value) })}
              />
              <Input
                label={t("anchorDate")}
                type="date"
                value={policy.cycle_anchor_date || ""}
                onChange={(event) => patch({ cycle_anchor_date: event.target.value || null })}
              />
            </>
          )}
        </div>

        {cycle && (
          <Alert
            variant="info"
            title={t("preservedPeriod")}
            description={(
              <span>
                {t("periodFrom")} <strong>{formatDate(cycle.period_start)}</strong> {t("periodTo")}{" "}
                <strong>{formatDate(cycle.period_end)}</strong>{t("periodChanges")}
              </span>
            )}
          />
        )}
      </Section>

      <Section
        appearance="card"
        title={t("automaticArchive")}
        description={t("archiveDescription")}
        actions={(
          <Switch
            aria-label={t("enableAutomations")}
            checked={policy.enabled}
            onCheckedChange={(checked) => patch({ enabled: checked })}
          />
        )}
      >
        <div className={styles.retentionTable}>
          <RetentionRow
            label={t("treated")}
            detail={t("treatedDetail")}
            enabled={policy.treated_archive_enabled}
            days={policy.treated_archive_days}
            onEnabled={(value) => patch({ treated_archive_enabled: value })}
            onDays={(value) => patch({ treated_archive_days: value })}
          />
          <RetentionRow
            label={t("rejected")}
            detail={t("rejectedDetail")}
            enabled={policy.rejected_archive_enabled}
            days={policy.rejected_archive_days}
            onEnabled={(value) => patch({ rejected_archive_enabled: value })}
            onDays={(value) => patch({ rejected_archive_days: value })}
          />
          <RetentionRow
            label={t("resolvedExternally")}
            detail={t("resolvedExternallyDetail")}
            enabled={policy.resolved_external_archive_enabled}
            days={policy.resolved_external_archive_days}
            onEnabled={(value) => patch({ resolved_external_archive_enabled: value })}
            onDays={(value) => patch({ resolved_external_archive_days: value })}
          />
          <RetentionRow
            label={t("open")}
            detail={t("openDetail")}
            enabled={policy.open_archive_enabled}
            days={policy.open_archive_days}
            onEnabled={(value) => patch({ open_archive_enabled: value })}
            onDays={(value) => patch({ open_archive_days: value })}
          />
        </div>
      </Section>

      <Section appearance="card" title={t("observationDetails")}>
        <div className={styles.singleField}>
          <Input
            label={t("retentionDays")}
            type="number"
            min={policy.cycle_mode === "CALENDAR_MONTH" ? 31 : Math.max(30, policy.cycle_length_days)}
            max={3650}
            value={policy.observation_retention_days}
            onChange={(event) => patch({ observation_retention_days: Number(event.target.value) })}
            helperText={t("retentionHelp")}
          />
        </div>
      </Section>

      {reductionWarning && (
        <Alert
          variant="warning"
          icon={<AlertTriangle {...iconDefaults} />}
          title={t("retentionReduction")}
          description={t("retentionWarning")}
        />
      )}

      <Section
        appearance="card"
        title={t("impactTitle")}
        description={t("impactDescription")}
        actions={(
          <div className={styles.actions}>
            <Button
              variant="secondary"
              leadingIcon={<Eye {...iconDefaults} />}
              onClick={() => void runPreview()}
              disabled={busy}
            >
              {t("previewAction")}
            </Button>
            <Button
              variant="primary"
              leadingIcon={<Save {...iconDefaults} />}
              onClick={() => void save()}
              loading={busy}
            >
              {t("savePolicy")}
            </Button>
          </div>
        )}
      >
        {preview ? (
          <div className={styles.preview}>
            <div className={styles.previewGrid}>
              <Metric label={t("treatedEligible")} value={preview.treated_eligible} />
              <Metric label={t("rejectedEligible")} value={preview.rejected_eligible} />
              <Metric label={t("resolvedEligible")} value={preview.resolved_externally_eligible} />
              <Metric label={t("openEligible")} value={preview.open_eligible} />
              <Metric label={t("observationsEligible")} value={preview.observations_eligible_for_purge} />
              <Metric label={t("overdueCycles")} value={preview.overdue_cycles_awaiting_close} />
            </div>
            {preview.warnings.map((warning) => (
              <Alert key={warning} variant="warning" description={warning} />
            ))}
          </div>
        ) : (
          <p className={styles.secondaryText}>{t("previewHelp")}</p>
        )}
      </Section>

      <Section appearance="card" title={t("lastRuns")}>
        <div className={styles.maintenanceGrid}>
          <MaintenanceItem label={t("retention")} value={formatDate(policy.maintenance.last_retention_run_at)} />
          <MaintenanceItem label={t("automaticClosure")} value={formatDate(policy.maintenance.last_cycle_close_check_at)} />
          <MaintenanceItem label={t("observationCleanup")} value={formatDate(policy.maintenance.last_observation_cleanup_at)} />
        </div>
      </Section>
    </div>
  );
}

function PolicyStatus({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card className={styles.statusCard}>
      <span className={styles.kicker}>{label}</span>
      <strong className={styles.statusValue}>{value}</strong>
      <span className={styles.statusMeta}>{detail}</span>
    </Card>
  );
}

function RetentionRow({
  label,
  detail,
  enabled,
  days,
  onEnabled,
  onDays,
}: {
  label: string;
  detail: string;
  enabled: boolean;
  days: number;
  onEnabled: (value: boolean) => void;
  onDays: (value: number) => void;
}) {
  const t = useTranslations("settings.opportunities");
  return (
    <div className={styles.retentionRow}>
      <div className={styles.retentionCopy}>
        <strong>{label}</strong>
        <span>{detail}</span>
      </div>
      <Switch
        aria-label={t("enableArchive", {label})}
        checked={enabled}
        onCheckedChange={onEnabled}
      />
      <div className={styles.afterDays}>
        <span>{t("after")}</span>
        <div className={styles.daysControl}>
          <Input
            aria-label={t("daysFor", {label})}
            type="number"
            min={1}
            max={3650}
            value={days}
            disabled={!enabled}
            onChange={(event) => onDays(Number(event.target.value))}
          />
        </div>
        <span>{t("days")}</span>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.metric}>
      <strong>{value.toLocaleString(useLocale())}</strong>
      <span>{label}</span>
    </div>
  );
}

function MaintenanceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.maintenanceItem}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
