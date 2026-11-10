"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { formatDate } from "@/lib/api";
import { formatNumber, providerLabel } from "@/lib/cloud.mjs";
import {
  buildContinuedHref,
  buildFirstSeenOpportunitiesHref,
  buildNewVsPreviousHref,
  buildNoLongerDetectedHref,
  buildObservedOpportunitiesHref,
  buildReappearedHref,
} from "@/lib/collection-query.mjs";
import { cachePolicy } from "@/lib/query-keys.mjs";
import { useApiQuery } from "@/lib/server-state";

type RunReference = {
  id: string;
  provider: string;
  account_id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  analyzer_version: string | null;
  detailed_observations_available: boolean;
};

type RunChanges = {
  collection_run_id: string;
  status: string;
  comparison_status: string;
  baseline_run_id: string | null;
  baseline: RunReference | null;
  comparable: boolean;
  reason: string | null;
  target_details_available: boolean;
  comparison_details_available: boolean;
  rules_version_changed: boolean | null;
  partial_coverage: boolean;
  coverage: {
    total_scopes: number;
    successful_scopes: number;
    failed_scopes: number;
    skipped_scopes: number;
    comparable_scopes: number;
  };
  scope_issues: Array<{
    provider: string;
    account_id: string;
    region: string;
    service: string | null;
    rule_key: string;
    status: string;
    error_detail: string | null;
  }>;
  summary: {
    observed: number;
    first_seen: number;
    new_vs_previous: number;
    reappeared: number;
    continued: number;
    no_longer_detected: number;
    operational_new_vs_previous: number;
  };
  warnings: Array<{ code: string; message: string }>;
};

type RunIdentity = {
  id: string;
  status: string;
  provider: string;
  account_id: string;
};

const number = (value: number, locale = "pt-BR") => formatNumber(value, locale);

function MetricLink({ href, label, value, title }: { href: string; label: string; value: number; title?: string }) {
  const locale = useLocale();
  return (
    <Link className="collection-link" href={href} title={title}>
      <strong>{number(value, locale)}</strong>
      <span>{label}</span>
    </Link>
  );
}

export function CollectionOpportunityInvestigation({ run }: { run: RunIdentity }) {
  const t = useTranslations("collections.investigation");
  const locale = useLocale();
  const request = useApiQuery<RunChanges>({
    key: ["collections", run.id, "opportunity-changes"],
    path: `/collections/${encodeURIComponent(run.id)}/opportunity-changes`,
    ...cachePolicy.detail,
  });

  if (request.isLoading) return <p role="status">{t("loading")}</p>;
  if (request.error || !request.data) {
    return (
      <div className="alert error" role="alert">
        {t("loadError")}
        <button className="button ghost" onClick={() => void request.refetch()}>{t("retry")}</button>
      </div>
    );
  }

  const data = request.data;
  const scope = { provider: run.provider, accountId: run.account_id };
  const comparisonAvailable = data.comparable;

  return (
    <section aria-label={t("ariaLabel")}>
      <div className="collection-toolbar">
        <h3>{t("title")}</h3>
        <span>{data.comparison_status === "PARTIAL" ? t("partial") : data.comparison_status}</span>
      </div>

      {data.comparison_status === "RUNNING" && (
        <div className="alert" role="status">
          <strong>{t("runningTitle")}</strong>
          <p>{t("runningDescription")}</p>
        </div>
      )}
      {data.comparison_status === "FAILED" && (
        <div className="alert error" role="status">
          <strong>{t("failedTitle")}</strong>
          <p>{t("failedDescription")}</p>
        </div>
      )}
      {data.comparison_status === "EXPIRED" && (
        <div className="alert" role="status">
          <strong>{t("expiredTitle")}</strong>
          <p>{t("expiredDescription")}</p>
        </div>
      )}

      {data.target_details_available && (
        <div className="collection-metadata">
          <div>
            <dt>{t("observed")}</dt>
            <dd><MetricLink href={buildObservedOpportunitiesHref(run.id, scope)} value={data.summary.observed} label={t("viewObserved")} /></dd>
          </div>
          <div>
            <dt>{t("firstSeen")}</dt>
            <dd><MetricLink href={buildFirstSeenOpportunitiesHref(run.id, scope)} value={data.summary.first_seen} label={t("viewFirstSeen")} /></dd>
          </div>
          {comparisonAvailable && (
            <>
              <div>
                <dt>{t("newVsPrevious")}</dt>
                <dd><MetricLink href={buildNewVsPreviousHref(run.id, scope)} value={data.summary.new_vs_previous} label={t("viewNewVsPrevious")} title={t("newDescription")} /></dd>
              </div>
              <div>
                <dt>{t("reappeared")}</dt>
                <dd><MetricLink href={buildReappearedHref(run.id, scope)} value={data.summary.reappeared} label={t("viewReappeared")} title={t("reappearedDescription")} /></dd>
              </div>
              <div>
                <dt>{t("continued")}</dt>
                <dd><MetricLink href={buildContinuedHref(run.id, scope)} value={data.summary.continued} label={t("viewContinued")} /></dd>
              </div>
              <div>
                <dt>{t("noLongerDetected")}</dt>
                <dd><MetricLink href={buildNoLongerDetectedHref(run.id, scope)} value={data.summary.no_longer_detected} label={t("viewNoLongerDetected")} title={t("noLongerDescription")} /></dd>
              </div>
            </>
          )}
        </div>
      )}

      {data.reason === "NO_BASELINE" && (
        <div className="alert" role="status">
          <strong>{t("noBaseline")}</strong>
          <p>{t("noBaselineDescription")}</p>
        </div>
      )}

      <div className="collection-toolbar">
        <h3>{t("comparisonTitle")}</h3>
        {data.baseline ? (
          <Link className="button ghost" href={`/collections/${encodeURIComponent(data.baseline.id)}`}>
            {t("openBaseline")}
          </Link>
        ) : null}
      </div>
      {data.baseline ? (
        <dl className="collection-metadata">
          <div><dt>Baseline</dt><dd>{formatDate(data.baseline.started_at, locale)}</dd></div>
          <div><dt>{t("cloud")}</dt><dd>{providerLabel(data.baseline.provider)}</dd></div>
          <div><dt>{t("account")}</dt><dd>{data.baseline.account_id}</dd></div>
          <div><dt>{t("status")}</dt><dd>{data.baseline.status === "SUCCESS" ? t("statusSuccess") : data.baseline.status === "FAILED" ? t("statusFailed") : data.baseline.status === "RUNNING" ? t("statusRunning") : data.baseline.status}</dd></div>
          <div><dt>{t("analyzerVersion")}</dt><dd>{data.baseline.analyzer_version || t("notRecorded")}</dd></div>
          <div><dt>Run</dt><dd><code>{data.baseline.id.slice(0, 8)}</code></dd></div>
        </dl>
      ) : (
        <p className="collection-note">{t("noBaselineUsed")}</p>
      )}

      <h3>{t("scopeCoverage")}</h3>
      <dl className="collection-metadata">
        <div><dt>{t("total")}</dt><dd>{number(data.coverage.total_scopes, locale)}</dd></div>
        <div><dt>{t("coverageSuccess")}</dt><dd>{number(data.coverage.successful_scopes, locale)}</dd></div>
        <div><dt>{t("coverageFailed")}</dt><dd>{number(data.coverage.failed_scopes, locale)}</dd></div>
        <div><dt>{t("coverageSkipped")}</dt><dd>{number(data.coverage.skipped_scopes, locale)}</dd></div>
        <div><dt>{t("comparable")}</dt><dd>{number(data.coverage.comparable_scopes, locale)}</dd></div>
      </dl>

      {data.warnings.map((warning) => (
        <div className="alert" role="status" key={warning.code}>
          <strong>{warning.code === "RULES_VERSION_CHANGED" ? t("rulesVersionsDiffer") : t("comparisonAttention")}</strong>
          <p>{warning.message}</p>
        </div>
      ))}

      {data.scope_issues.length > 0 && (
        <div>
          <h3>{t("scopesUnsuccessful")}</h3>
          <div className="data-table-wrap" tabIndex={0} role="region" aria-label={t("scopesUnsuccessful")}>
            <table className="data-table">
              <thead><tr><th>{t("scope")}</th><th>{t("status")}</th><th>{t("error")}</th></tr></thead>
              <tbody>
                {data.scope_issues.map((issue) => (
                  <tr key={`${issue.provider}:${issue.account_id}:${issue.region}:${issue.rule_key}`}>
                    <td>{issue.region} · {issue.service || issue.rule_key}<span>{issue.rule_key}</span></td>
                    <td>{issue.status === "SUCCESS" ? t("statusSuccess") : issue.status === "FAILED" ? t("statusFailed") : issue.status === "RUNNING" ? t("statusRunning") : issue.status}</td>
                    <td>{issue.error_detail || t("noDetails")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
