"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { BrainCircuit, Check, Copy, RotateCcw } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { FindingEvidence } from "@/components/finding-evidence";
import { OpportunityArchiveHistory } from "@/components/opportunity-archive-history";
import { OpportunityPresenceHistory } from "@/components/opportunity-presence-history";
import type { OpportunityDecisionAction } from "@/components/opportunity-decision-dialog";
import {
  CurrencyDisplay,
  ProviderBadge,
  ResourceIdentifier,
  StatusIndicator,
} from "@/components/aven";
import type { ProductStatus } from "@/components/aven";
import {
  Alert,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  Pagination,
  Skeleton,
} from "@/components/ui";
import { api, formatDate } from "@/lib/api";
import { formatAccountLabel } from "@/lib/cloud.mjs";
import { iconDefaults } from "@/lib/iconography";
import { cachePolicy, queryKeys } from "@/lib/query-keys.mjs";
import { invalidateApiQueries, useApiQuery } from "@/lib/server-state";
import type {
  OpportunityDetail as OpportunityDetailType,
  OpportunityObservation,
  OpportunityObservationPage,
  OpportunityStatusHistoryPage,
} from "@/lib/types";
import styles from "./opportunity-detail.module.css";

type HistoricalOpportunityDetail = OpportunityDetailType & {
  archived: boolean;
  archived_at: string | null;
  archived_by: string | null;
  archive_reason: string | null;
  first_seen_collection_run_id: string | null;
  last_seen_collection_run_id: string | null;
};

type Props = {
  opportunityId: string;
  onClose: () => void;
  onAction: (action: OpportunityDecisionAction, id: string) => void;
  onArchive: (id: string) => void;
};

function numericValue(value: string | number | null | undefined) {
  if (value == null || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function statusTone(value: string): ProductStatus {
  if (value === "treated" || value === "active" || value === "resolved_externally") return "success";
  if (value === "rejected") return "danger";
  if (value === "missing") return "warning";
  if (value === "open") return "info";
  return "neutral";
}

function severityTone(value: string): ProductStatus {
  if (value === "high") return "danger";
  if (value === "medium") return "warning";
  if (value === "low") return "info";
  return "neutral";
}

function confidenceTone(value: string): ProductStatus {
  const normalized = value.trim().toLowerCase();
  if (normalized === "high") return "success";
  if (normalized === "medium") return "info";
  if (normalized === "low") return "warning";
  return "neutral";
}

function humanize(value?: string | null) {
  if (!value) return "—";
  return value.split("_").filter(Boolean).map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()).join(" ");
}

function technicalValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value, null, 2) ?? String(value);
}

function MoneyValue({ value, currency }: { value: string | number | null | undefined; currency: string }) {
  const locale = useLocale();
  const amount = numericValue(value);
  if (!currency || amount == null) return <span>—</span>;
  return <CurrencyDisplay value={amount} currency={currency} locale={locale} maximumFractionDigits={2} />;
}

function MonthlySavings({ detail }: { detail: OpportunityDetailType }) {
  const t = useTranslations("opportunities.detail");
  if (detail.rule_key === "cost_growth_anomaly") return <span>{t("savings.notEstimated")}</span>;
  return <><MoneyValue value={detail.estimated_monthly_savings} currency={detail.currency} />{t("savings.perMonth")}</>;
}

export function OpportunityDetail({ opportunityId, onClose, onAction, onArchive }: Props) {
  const t = useTranslations("opportunities.detail");
  const status = useTranslations("opportunities.status");
  const severity = useTranslations("opportunities.severity");
  const reason = useTranslations("opportunities.decision.reason");
  const statusLabel = (value: string) => value === "resolved_externally" ? status("resolvedExternally") : ["open","treated","rejected","active","missing"].includes(value) ? status(value as "open" | "treated" | "rejected" | "active" | "missing") : humanize(value);
  const severityLabel = (value: string) => ["high","medium","low"].includes(value.toLowerCase()) ? severity(value.toLowerCase() as "high" | "medium" | "low") : humanize(value);
  const rejectionReasonLabels: Record<string,string> = {FALSE_POSITIVE:reason("falsePositive"),OPERATIONAL_EXCEPTION:reason("operationalException"),ACCEPTABLE_COST:reason("acceptableCost"),RESOURCE_REQUIRED:reason("resourceRequired"),RISK_ACCEPTED:reason("riskAccepted"),OTHER:reason("other")};
  const archiveReasonLabels: Record<string,string> = {MANUAL:t("archiveReason.manual"),RETENTION_POLICY:t("archiveReason.retentionPolicy")};
  const [selectedObservation, setSelectedObservation] = useState<OpportunityObservation | null>(null);
  const [actionError, setActionError] = useState("");
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);
  const [aiInsight, setAiInsight] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [unarchiveSaving, setUnarchiveSaving] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);
  const [copiedTechnicalKey, setCopiedTechnicalKey] = useState("");
  const copyTimeoutRef = useRef<number | null>(null);
  const historyPageSize = historyExpanded ? 50 : 8;

  const detailRequest = useApiQuery<HistoricalOpportunityDetail>({
    key: queryKeys.opportunities.detail(opportunityId),
    path: `/opportunities/${opportunityId}`,
    ...cachePolicy.detail,
  });
  const observationRequest = useApiQuery<OpportunityObservationPage>({
    key: queryKeys.opportunities.history(opportunityId, historyPage, historyPageSize),
    path: `/opportunities/${opportunityId}/history?page=${historyPage}&page_size=${historyPageSize}`,
    ...cachePolicy.detail,
    keepPreviousData: true,
    placeholderIdentity: `${opportunityId}:${historyPageSize}`,
  });
  const decisionRequest = useApiQuery<OpportunityStatusHistoryPage>({
    key: queryKeys.opportunities.statusHistory(opportunityId),
    path: `/opportunities/${opportunityId}/status-history?page=1&page_size=50`,
    ...cachePolicy.detail,
  });

  const detail = detailRequest.data ?? null;
  const observations = observationRequest.data ?? null;
  const decisions = decisionRequest.data ?? null;
  const loading = detailRequest.isLoading;
  const detailError = detailRequest.error?.message || "";
  const observationError = observationRequest.error ? t("observationError") : "";
  const decisionError = decisionRequest.error ? t("decisionError") : "";
  const error = actionError || detailError || observationError || decisionError;

  useEffect(() => {
    setSelectedObservation(null);
    setHistoryPage(1);
    setHistoryExpanded(false);
    setAiInsight("");
    setActionError("");
    setCopiedTechnicalKey("");
  }, [opportunityId]);

  useEffect(() => () => {
    if (copyTimeoutRef.current != null) window.clearTimeout(copyTimeoutRef.current);
  }, []);

  const currentDecision = useMemo(() => {
    if (!detail || !decisions) return null;
    return decisions.items.find((item) => item.to_status === detail.status) || null;
  }, [decisions, detail]);

  const providerMetadataEntries = useMemo(
    () => Object.entries(detail?.provider_metadata ?? {}).sort(([left], [right]) => left.localeCompare(right)),
    [detail?.provider_metadata],
  );

  async function copyTechnical(key: string, value: string) {
    if (!value || value === "—" || !navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(value);
      setCopiedTechnicalKey(key);
      if (copyTimeoutRef.current != null) window.clearTimeout(copyTimeoutRef.current);
      copyTimeoutRef.current = window.setTimeout(() => {
        setCopiedTechnicalKey((current) => current === key ? "" : current);
      }, 1600);
    } catch {
      setCopiedTechnicalKey("");
    }
  }

  async function explain() {
    if (!detail || aiLoading) return;
    setAiLoading(true);
    setAiInsight("");
    setActionError("");
    try {
      const result = await api<{ explanation: string }>(`/findings/${detail.id}/explain`, { method: "POST" });
      setAiInsight(result.explanation);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t("aiError"));
    } finally {
      setAiLoading(false);
    }
  }

  async function restoreArchivedCurrent() {
    if (!detail?.archived || unarchiveSaving) return;
    const isRejected = detail.status === "rejected";
    setUnarchiveSaving(true);
    setActionError("");
    try {
      if (isRejected) {
        await api(`/opportunities/${detail.id}/reopen`, { method: "POST", body: JSON.stringify({}) });
      } else {
        await api(`/opportunities/${detail.id}/unarchive`, { method: "POST" });
      }
      invalidateApiQueries(queryKeys.opportunities.all);
      invalidateApiQueries(queryKeys.dashboard.all);
      setRestoreOpen(false);
      onClose();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : isRejected ? t("reopenError") : t("unarchiveError"));
    } finally {
      setUnarchiveSaving(false);
    }
  }

  return (
    <>
      <Drawer open onOpenChange={(open) => { if (!open) onClose(); }}>
        <DrawerContent side="right" size="wide">
          <DrawerHeader>
            <DrawerTitle>{detail?.title || t("loadingTitle")}</DrawerTitle>
            <DrawerDescription>{detail ? detail.description : t("loadingDescription")}</DrawerDescription>
          </DrawerHeader>

          <div className={styles.body}>
            {error ? <Alert variant="danger" title={t("contextError")} description={error} /> : null}
            {loading && !detail ? <><Skeleton /><Skeleton /><Skeleton /></> : null}

            {detail ? (
              <>
                <section className={styles.overview} aria-label={t("overviewAria")}>
                  <div className={styles.statusLine}>
                    <ProviderBadge provider={detail.provider} />
                    <StatusIndicator status={statusTone(detail.status)} label={statusLabel(detail.status)} />
                    <StatusIndicator status={statusTone(detail.presence_status)} label={statusLabel(detail.presence_status)} />
                    <StatusIndicator status={severityTone(detail.severity)} label={t("impact",{value:severityLabel(detail.severity)})} />
                    {detail.confidence ? <StatusIndicator status={confidenceTone(detail.confidence)} label={t("confidence",{value:severityLabel(detail.confidence)})} /> : null}
                    {detail.archived ? <StatusIndicator status="neutral" label={t("archived")} /> : null}
                    {detail.needs_review ? <StatusIndicator status="warning" label={t("detectedAgain")} /> : null}
                  </div>

                  <ResourceIdentifier
                    primary={detail.resource_name || detail.resource_id}
                    technicalId={detail.resource_name ? detail.resource_id : undefined}
                    copyValue={detail.resource_id}
                    copyLabel={t("copyResource")}
                    copiedLabel={t("copiedResource")}
                  />

                  {detail.status === "rejected" && detail.archived && detail.presence_status === "active" ? (
                    <Alert variant="warning" title={t("rejectedActiveTitle")} description={t("rejectedActiveDescription")} />
                  ) : null}

                  <dl className={styles.detailGrid}>
                    <div><dt>{t("field.account")}</dt><dd>{formatAccountLabel(detail.account_name, detail.account_id)}</dd></div>
                    <div><dt>{t("field.region")}</dt><dd>{detail.region || "—"}</dd></div>
                    <div><dt>{t("field.service")}</dt><dd>{detail.service || "—"}</dd></div>
                    {detail.resource_type ? <div><dt>{t("field.resourceType")}</dt><dd>{detail.resource_type}</dd></div> : null}
                    <div><dt>{t("field.rule")}</dt><dd>{detail.rule.name}<span className={styles.secondary}>{detail.rule.description}</span></dd></div>
                    <div><dt>{t("field.potential")}</dt><dd><MonthlySavings detail={detail} /></dd></div>
                    <div><dt>{t("field.currentCost")}</dt><dd><MoneyValue value={detail.current_monthly_cost} currency={detail.currency} /></dd></div>
                    <div><dt>{t("field.confidence")}</dt><dd>{detail.confidence ? severityLabel(detail.confidence) : "—"}</dd></div>
                    <div><dt>{t("field.firstSeen")}</dt><dd>{formatDate(detail.first_seen_at)}{detail.first_seen_collection_run_id ? <span className={styles.secondary}><Link href={`/collections/${encodeURIComponent(detail.first_seen_collection_run_id)}`}>{t("openFirstCollection")} {detail.first_seen_collection_run_id.slice(0, 8)}</Link></span> : null}</dd></div>
                    <div><dt>{t("field.lastSeen")}</dt><dd>{formatDate(detail.last_seen_at)}{detail.last_seen_collection_run_id ? <span className={styles.secondary}><Link href={`/collections/${encodeURIComponent(detail.last_seen_collection_run_id)}`}>{t("openLastCollection")} {detail.last_seen_collection_run_id.slice(0, 8)}</Link></span> : null}</dd></div>
                    {detail.treated_at ? <div><dt>{t("field.treatedAt")}</dt><dd>{formatDate(detail.treated_at)}</dd></div> : null}
                    {detail.rejected_at ? <div><dt>{t("field.rejectedAt")}</dt><dd>{formatDate(detail.rejected_at)}</dd></div> : null}
                    {detail.resolved_externally_at ? <div><dt>{t("field.resolvedExternallyAt")}</dt><dd>{formatDate(detail.resolved_externally_at)}</dd></div> : null}
                    {detail.archived ? <div><dt>{t("field.archivedAt")}</dt><dd>{formatDate(detail.archived_at)}</dd></div> : null}
                    {detail.archived ? <div><dt>{t("field.archiveReason")}</dt><dd>{archiveReasonLabels[detail.archive_reason || ""] || detail.archive_reason || "—"}</dd></div> : null}
                    <div><dt>{t("field.occurrences")}</dt><dd>{detail.total_occurrence_count}</dd></div>
                    <div><dt>{t("field.retained")}</dt><dd>{observations?.retained_total ?? "—"}</dd></div>
                  </dl>
                </section>

                {(detail.status === "treated" || detail.status === "rejected") ? (
                  <section className={styles.section} aria-labelledby="decision-summary-title">
                    <div className={styles.sectionHeader}>
                      <div><h3 id="decision-summary-title">{t("decision.title")}</h3><p>{t("decision.description")}</p></div>
                      <StatusIndicator status={statusTone(detail.status)} label={statusLabel(detail.status)} />
                    </div>
                    <dl className={styles.decisionGrid}>
                      <div><dt>{t("decision.by")}</dt><dd>{currentDecision?.changed_by_name || t("decision.notRecorded")}</dd></div>
                      <div><dt>{t("decision.date")}</dt><dd>{formatDate(currentDecision?.changed_at ?? (detail.status === "treated" ? detail.treated_at : detail.rejected_at) ?? null)}</dd></div>
                      {detail.status === "rejected" ? <div><dt>{t("decision.reason")}</dt><dd>{rejectionReasonLabels[detail.rejection_reason || ""] || detail.rejection_reason || t("decision.notRecorded")}</dd></div> : null}
                      <div className={styles.decisionNote}><dt>{t("decision.note")}</dt><dd>{currentDecision?.note || (detail.status === "treated" ? detail.treatment_note : detail.rejection_note) || t("decision.noNote")}</dd></div>
                    </dl>
                  </section>
                ) : null}

                <section className={styles.section} aria-labelledby="evidence-title">
                  <div className={styles.sectionHeader}><div><h3 id="evidence-title">{t("evidence.title")}</h3><p>Métricas e fatos persistidos pela recomendação; nenhum valor é recalculado na interface.</p></div></div>
                  {selectedObservation ? (
                    <div className={styles.historicalBanner}>
                      <strong>{t("evidence.historical")}</strong>
                      <span>{t("evidence.collectionDate",{date:formatDate(selectedObservation.observed_at)})}</span>
                      <Button variant="ghost" size="sm" onClick={() => setSelectedObservation(null)}>{t("evidence.backToLatest")}</Button>
                    </div>
                  ) : null}
                  <FindingEvidence
                    evidence={selectedObservation?.evidence ?? detail.latest_evidence}
                    observedAt={selectedObservation?.observed_at ?? detail.latest_observation?.observed_at ?? detail.last_seen_at}
                    collectionRunId={selectedObservation?.collection_run_id ?? detail.latest_observation?.collection_run_id ?? null}
                  />
                  <div className={styles.actions}>
                    <Button variant="outline" size="sm" leadingIcon={<BrainCircuit {...iconDefaults} />} loading={aiLoading} onClick={() => void explain()}>{t("evidence.ai")}</Button>
                  </div>
                  {aiInsight ? <div className={styles.aiResult}>{aiInsight}</div> : null}
                </section>

                <section className={styles.section} aria-labelledby="detection-history-title">
                  <div className={styles.sectionHeader}>
                    <div><h3 id="detection-history-title">{t("detection.title")}</h3><p>{t("detection.description")}</p></div>
                    {observations ? <span className={styles.secondary}>{t("detection.retained",{details:observations.retained_total,occurrences:observations.total_occurrence_count})}</span> : null}
                  </div>
                  {observations && !observations.history_complete ? <Alert variant="warning" title={t("detection.partialTitle")} description={t("detection.partialDescription",{days:observations.retention_days})} /> : null}
                  {observationRequest.isLoading ? <Skeleton /> : observations?.items.length ? (
                    <div className={styles.historyList}>
                      {observations.items.map((item) => (
                        <article key={item.id} className={styles.historyItem} data-selected={selectedObservation?.id === item.id || undefined}>
                          <div className={styles.historyTop}>
                            <div className={styles.historyMetric}><strong>{formatDate(item.observed_at)}</strong><span className={styles.secondary}>{item.collection_provider} · {item.collection_account_id}</span></div>
                            <StatusIndicator status={severityTone(item.severity)} label={t("impact",{value:severityLabel(item.severity)})} />
                            <div className={styles.historyMetric}><strong><MoneyValue value={item.estimated_monthly_savings} currency={item.currency} />{t("savings.perMonth")}</strong><span className={styles.secondary}>{t("detection.estimatedSavings")}</span></div>
                          </div>
                          <p className={styles.secondary}>{item.evidence.summary}</p>
                          <div className={styles.historyActions}>
                            <Button variant="ghost" size="sm" onClick={() => setSelectedObservation(item)}>{t("detection.viewEvidence")}</Button>
                            <Button variant="ghost" size="sm" onClick={() => { window.location.href = `/collections/${encodeURIComponent(item.collection_run_id)}`; }}>{t("detection.openCollection")} {item.collection_run_id.slice(0, 8)}</Button>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : <p className={styles.secondary}>{observations && !observations.history_complete ? t("detection.noRetained") : t("detection.empty")}</p>}
                  {observations && !historyExpanded && observations.retained_total > 8 ? <Button variant="ghost" size="sm" onClick={() => { setHistoryPage(1); setHistoryExpanded(true); }}>{t("detection.full")}</Button> : null}
                  {observations && historyExpanded && observations.total_pages > 1 ? <Pagination page={observations.page} pageCount={observations.total_pages} onPageChange={setHistoryPage} /> : null}
                </section>

                <OpportunityPresenceHistory opportunityId={opportunityId} />
                <OpportunityArchiveHistory opportunityId={opportunityId} />

                <section className={styles.section} aria-labelledby="decision-history-title">
                  <div className={styles.sectionHeader}><div><h3 id="decision-history-title">{t("history.title")}</h3><p>{t("history.description")}</p></div>{decisions ? <span className={styles.secondary}>{t("history.count",{count:decisions.total})}</span> : null}</div>
                  {decisionRequest.isLoading ? <Skeleton /> : decisions?.items.length ? (
                    <div className={styles.decisionHistory}>
                      {decisions.items.map((item) => (
                        <article key={item.id} className={styles.decisionItem}>
                          <strong>{formatDate(item.changed_at)} · {item.changed_by_name || t("history.unknownUser")}</strong>
                          <div className={styles.metadataLine}><StatusIndicator status={statusTone(item.from_status)} label={statusLabel(item.from_status)} /><span aria-hidden="true">→</span><StatusIndicator status={statusTone(item.to_status)} label={statusLabel(item.to_status)} /></div>
                          {item.reason ? <span className={styles.secondary}>{t("history.reason")} {rejectionReasonLabels[item.reason] || item.reason}</span> : null}
                          {item.note ? <p className={styles.secondary}>{item.note}</p> : null}
                        </article>
                      ))}
                    </div>
                  ) : <p className={styles.secondary}>Nenhuma decisão manual registrada.</p>}
                </section>

                <details className={styles.technicalDetails}>
                  <summary>{t("technical.title")}</summary>
                  <dl className={styles.technicalGrid}>
                    <div>
                      <dt>{t("technical.resourceId")}</dt>
                      <dd><code>{detail.resource_id}</code><Button variant="ghost" size="sm" leadingIcon={copiedTechnicalKey === "resource-id" ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />} onClick={() => void copyTechnical("resource-id", detail.resource_id)}>{copiedTechnicalKey === "resource-id" ? t("technical.copied") : t("technical.copy")}</Button></dd>
                    </div>
                    <div>
                      <dt>{t("technical.accountId")}</dt>
                      <dd><code>{detail.account_id}</code><Button variant="ghost" size="sm" leadingIcon={copiedTechnicalKey === "account-id" ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />} onClick={() => void copyTechnical("account-id", detail.account_id)}>{copiedTechnicalKey === "account-id" ? t("technical.copied") : t("technical.copy")}</Button></dd>
                    </div>
                    <div>
                      <dt>{t("technical.opportunityId")}</dt>
                      <dd><code>{detail.id}</code><Button variant="ghost" size="sm" leadingIcon={copiedTechnicalKey === "opportunity-id" ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />} onClick={() => void copyTechnical("opportunity-id", detail.id)}>{copiedTechnicalKey === "opportunity-id" ? t("technical.copied") : t("technical.copy")}</Button></dd>
                    </div>
                    <div>
                      <dt>Fingerprint</dt>
                      <dd><code>{detail.fingerprint}</code><Button variant="ghost" size="sm" leadingIcon={copiedTechnicalKey === "fingerprint" ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />} onClick={() => void copyTechnical("fingerprint", detail.fingerprint)}>{copiedTechnicalKey === "fingerprint" ? t("technical.copied") : t("technical.copy")}</Button></dd>
                    </div>
                    <div><dt>{t("technical.rule")}</dt><dd><code>{detail.rule.key}</code></dd></div>
                    <div><dt>{t("technical.legacyScan")}</dt><dd><code>{detail.scan_id || "—"}</code></dd></div>
                    <div><dt>{t("technical.firstCollection")}</dt><dd><code>{detail.first_seen_collection_run_id || "—"}</code></dd></div>
                    <div><dt>{t("technical.lastCollection")}</dt><dd><code>{detail.last_seen_collection_run_id || "—"}</code></dd></div>
                    {providerMetadataEntries.map(([key, value]) => {
                      const formattedValue = technicalValue(value);
                      const copyKey = `provider-${key}`;
                      const structured = typeof value === "object" && value !== null;
                      return (
                        <div key={key}>
                          <dt>{humanize(key)}</dt>
                          <dd>
                            {structured ? <pre>{formattedValue}</pre> : <code>{formattedValue}</code>}
                            {formattedValue !== "—" ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                leadingIcon={copiedTechnicalKey === copyKey ? <Check {...iconDefaults} /> : <Copy {...iconDefaults} />}
                                onClick={() => void copyTechnical(copyKey, formattedValue)}
                              >
                                {copiedTechnicalKey === copyKey ? t("technical.copied") : t("technical.copy")}
                              </Button>
                            ) : null}
                          </dd>
                        </div>
                      );
                    })}
                  </dl>
                </details>
              </>
            ) : null}
          </div>

          {detail ? (
            <DrawerFooter>
              {detail.archived ? (
                <Button variant="primary" leadingIcon={<RotateCcw {...iconDefaults} />} onClick={() => setRestoreOpen(true)}>{detail.status === "rejected" ? t("actions.reopenOpportunity") : t("actions.unarchive")}</Button>
              ) : detail.status === "open" ? (
                <div className={styles.actions}>
                  <Button variant="outline" onClick={() => onAction("treat", detail.id)}>{t("actions.treat")}</Button>
                  <Button variant="ghost" onClick={() => onArchive(detail.id)}>{t("actions.archive")}</Button>
                  <Button variant="danger" onClick={() => onAction("reject", detail.id)}>{t("actions.reject")}</Button>
                </div>
              ) : (
                <div className={styles.actions}>
                  <Button variant="ghost" onClick={() => onArchive(detail.id)}>{t("actions.archive")}</Button>
                  <Button variant="primary" leadingIcon={<RotateCcw {...iconDefaults} />} onClick={() => onAction("reopen", detail.id)}>{t("actions.reopen")}</Button>
                </div>
              )}
            </DrawerFooter>
          ) : null}
        </DrawerContent>
      </Drawer>

      {detail?.archived ? (
        <Dialog open={restoreOpen} onOpenChange={(open) => { if (!unarchiveSaving) setRestoreOpen(open); }}>
          <DialogContent onCancel={(event) => { if (unarchiveSaving) event.preventDefault(); }}>
            <DialogHeader>
              <DialogTitle>{detail.status === "rejected" ? t("actions.reopenOpportunity") : t("actions.unarchiveOpportunity")}</DialogTitle>
              <DialogDescription>
                {detail.status === "rejected"
                  ? t("actions.reopenDescription")
                  : t("actions.unarchiveDescription")}
              </DialogDescription>
            </DialogHeader>
            {actionError ? <Alert variant="danger" title={t("actions.restoreError")} description={actionError} /> : null}
            <DialogFooter>
              <Button variant="secondary" disabled={unarchiveSaving} onClick={() => setRestoreOpen(false)}>{t("actions.cancel")}</Button>
              <Button variant="primary" loading={unarchiveSaving} onClick={() => void restoreArchivedCurrent()}>{detail.status === "rejected" ? t("actions.reopen") : t("actions.unarchive")}</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      ) : null}
    </>
  );
}
