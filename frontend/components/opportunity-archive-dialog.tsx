"use client";

import { useEffect, useMemo, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { CurrencyDisplay } from "@/components/aven";
import {
  Alert,
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Skeleton,
} from "@/components/ui";
import { api } from "@/lib/api";
import styles from "./opportunity-dialog.module.css";

type ArchiveFilters = {
  provider?: string;
  account_id?: string;
  region?: string;
  service?: string;
  resource_type?: string;
  status?: string;
  presence_status?: string;
  severity?: string;
  rule?: string;
  collection_run_id?: string;
  resource_id?: string;
  search?: string;
  current?: boolean;
};

type Preview = {
  matched: number;
  to_archive: number;
  already_archived: number;
  by_status: Record<string, number>;
  by_provider: Record<string, number>;
  by_account: Record<string, number>;
  savings: Array<{ currency: string; amount: string | number }>;
  filter_hash: string;
};

type ArchiveResult = {
  archived: number;
  already_archived: number;
  correlation_id: string;
  cycle_closed?: boolean;
  snapshots_created?: number;
  collection_runs?: number;
  failed_collection_runs?: number;
};

type Coverage = {
  total: number;
  success: number;
  failed: number;
  running: number;
};

type Cycle = {
  id: string;
  label: string;
  status: "OPEN" | "CLOSED";
  snapshot_count: number;
  coverage: Coverage;
};

type CycleClosePreview = {
  cycle_id: string;
  label: string;
  snapshots_to_create: number;
  coverage: Coverage;
};

type Props = {
  mode: "individual" | "selected" | "filter" | "period";
  opportunityId?: string;
  opportunityIds?: string[];
  filters?: ArchiveFilters;
  filterLabels?: string[];
  onClose: () => void;
  onSuccess: (message: string) => void;
};

export function OpportunityArchiveDialog({
  mode,
  opportunityId,
  opportunityIds = [],
  filters = {},
  filterLabels = [],
  onClose,
  onSuccess,
}: Props) {
  const t = useTranslations("opportunities.archive");
  const locale = useLocale();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [cycle, setCycle] = useState<Cycle | null>(null);
  const [cyclePreview, setCyclePreview] = useState<CycleClosePreview | null>(null);
  const [loading, setLoading] = useState(mode === "filter" || mode === "period");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const archiveAll = useMemo(
    () => !Object.values(filters).some((value) => value !== undefined && value !== "" && value !== false),
    [filters],
  );

  useEffect(() => {
    if (mode !== "filter" && mode !== "period") return;
    let cancelled = false;
    setLoading(true);
    setError("");
    void (async () => {
      try {
        const archivePreviewPromise = api<Preview>("/opportunities/archive-preview", {
          method: "POST",
          body: JSON.stringify({ filters, archive_all: archiveAll }),
        });
        if (mode === "filter") {
          const archivePreview = await archivePreviewPromise;
          if (!cancelled) {
            setPreview(archivePreview);
            setCycle(null);
            setCyclePreview(null);
          }
          return;
        }

        const currentCycle = await api<Cycle>("/opportunity-history/cycles/current");
        const [archivePreview, closePreview] = await Promise.all([
          archivePreviewPromise,
          api<CycleClosePreview>(`/opportunity-history/cycles/${currentCycle.id}/close-preview`),
        ]);
        if (!cancelled) {
          setPreview(archivePreview);
          setCycle(currentCycle);
          setCyclePreview(closePreview);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "__PREVIEW_FAILED__");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [archiveAll, filters, mode]);

  async function confirm() {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      if (mode === "individual") {
        if (!opportunityId) throw new Error(t("errors.opportunityMissing"));
        await api(`/opportunities/${opportunityId}/archive`, { method: "POST" });
        onSuccess(t("success.one"));
        return;
      }
      if (mode === "selected") {
        const result = await api<ArchiveResult>("/opportunities/bulk/archive", {
          method: "POST",
          body: JSON.stringify({ opportunity_ids: opportunityIds }),
        });
        onSuccess(t("success.bulk", {count:result.archived,already:result.already_archived}));
        return;
      }
      if (!preview || preview.to_archive === 0) return;
      if (mode === "period") {
        if (!cycle) throw new Error(t("errors.cycleMissing"));
        const result = await api<ArchiveResult>("/opportunities/period-close", {
          method: "POST",
          body: JSON.stringify({ cycle_id: cycle.id, filters, archive_all: archiveAll }),
        });
        onSuccess(t("success.period", {period:cycle.label,snapshots:result.snapshots_created ?? 0,archived:result.archived}));
        return;
      }
      const result = await api<ArchiveResult>("/opportunities/archive-by-filter", {
        method: "POST",
        body: JSON.stringify({ filters, archive_all: archiveAll }),
      });
      onSuccess(t("success.bulk", {count:result.archived,already:result.already_archived}));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.archiveFailed"));
    } finally {
      setSaving(false);
    }
  }

  const selectedCount = opportunityIds.length;
  const title = mode === "individual"
    ? t("titleOne")
    : mode === "selected"
      ? t("titleSelected", {count:selectedCount})
      : mode === "period"
        ? t("titlePeriod")
        : archiveAll
          ? t("titleAll")
          : t("titleFiltered");
  const periodCoverage = cyclePreview?.coverage ?? cycle?.coverage;
  const blockedByRunning = mode === "period" && Boolean(periodCoverage?.running);
  const disabled = saving || loading || ((mode === "filter" || mode === "period") && (!preview || preview.to_archive === 0)) || blockedByRunning;

  return (
    <Dialog open onOpenChange={(open) => { if (!open && !saving) onClose(); }}>
      <DialogContent onCancel={(event) => { if (saving) event.preventDefault(); }}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {mode === "individual"
              ? t("descriptionOne")
              : mode === "selected"
                ? t("descriptionSelected", {count:selectedCount})
                : mode === "period"
                  ? t("descriptionPeriod")
                  : t("descriptionFiltered")}
          </DialogDescription>
        </DialogHeader>

        <div className={styles.body}>
          {(mode === "filter" || mode === "period") && loading ? <><Skeleton /><Skeleton /><Skeleton /></> : null}

          {(mode === "filter" || mode === "period") && preview ? (
            <>
              {archiveAll ? <Alert variant="warning" title={t("scopeAllTitle")} description={t("scopeAllDescription")} /> : null}

              <dl className={styles.detailGrid}>
                {mode === "period" && cycle ? <div><dt>{t("field.period")}</dt><dd>{cycle.label}</dd></div> : null}
                <div><dt>{t("field.matched")}</dt><dd>{preview.matched}</dd></div>
                <div><dt>{t("field.toArchive")}</dt><dd>{preview.to_archive}</dd></div>
                <div><dt>{t("field.archived")}</dt><dd>{preview.already_archived}</dd></div>
                {mode === "period" && cyclePreview ? <div><dt>{t("field.snapshots")}</dt><dd>{cyclePreview.snapshots_to_create}</dd></div> : null}
                {mode === "period" && periodCoverage ? <div><dt>{t("field.collections")}</dt><dd>{periodCoverage.total}</dd></div> : null}
                {mode === "period" && periodCoverage ? <div><dt>{t("field.failed")}</dt><dd>{periodCoverage.failed}</dd></div> : null}
              </dl>

              {filterLabels.length > 0 ? (
                <div className={styles.activeFilterSummary} aria-label={t("aria.filters")}>
                  {filterLabels.map((label) => <Badge key={label} variant="neutral">{label}</Badge>)}
                </div>
              ) : null}

              {preview.savings.length > 0 ? (
                <div className={styles.savingsList} aria-label={t("aria.savings")}>
                  {preview.savings.map((item) => (
                    <Badge key={item.currency} variant="info">
                      <CurrencyDisplay value={Number(item.amount)} currency={item.currency} locale={locale} maximumFractionDigits={2} />
                    </Badge>
                  ))}
                </div>
              ) : null}

              <p className={styles.secondary}>{t("previewWarning")}</p>

              {preview.to_archive === 0 ? <Alert variant="info" title={t("emptyTitle")} description={t("emptyDescription")} /> : null}
              {mode === "period" && periodCoverage && periodCoverage.failed > 0 ? <Alert variant="warning" title={t("failedTitle")} description={t("failedDescription",{count:periodCoverage.failed})} /> : null}
              {blockedByRunning ? <Alert variant="danger" title={t("blockedTitle")} description={t("blockedDescription",{count:periodCoverage?.running ?? 0})} /> : null}
            </>
          ) : null}

          {error ? <Alert variant="danger" title={t("errorTitle")} description={error === "__PREVIEW_FAILED__" ? t("errors.preview") : error} /> : null}
        </div>

        <DialogFooter>
          <Button variant="secondary" type="button" disabled={saving} onClick={onClose}>{t("cancel")}</Button>
          <Button variant="primary" type="button" disabled={disabled} loading={saving} onClick={() => void confirm()}>
            {mode === "period"
              ? (preview ? t("submitPeriodArchive",{count:preview.to_archive}) : t("submitPeriod"))
              : mode === "filter"
                ? t("submitCount",{count:preview?.to_archive ?? 0})
                : mode === "selected"
                  ? t("submitCount",{count:selectedCount})
                  : t("titleOne")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
