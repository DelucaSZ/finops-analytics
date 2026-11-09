import { formatDate } from "@/lib/api";
import { useLocale, useTranslations } from "next-intl";
import { PRODUCT_NAME } from "@/lib/brand";
import type {
  EvidenceCriterion,
  EvidenceMetric,
  OpportunityEvidence,
} from "@/lib/types";

type Props = {
  evidence: OpportunityEvidence | null;
  observedAt?: string | null;
  collectionRunId?: string | null;
};

type EvidencePresentation = {
  locale: string;
  notRecorded: string;
  yes: string;
  no: string;
  none: string;
  observedUnavailable: string;
  perMonth: string;
  units: Record<string,string>;
};

function displayScalar(value: unknown, labels: EvidencePresentation): string {
  if (value === null || value === undefined) return labels.notRecorded;
  if (typeof value === "boolean") return value ? labels.yes : labels.no;
  if (typeof value === "number") return value.toLocaleString(labels.locale, {maximumFractionDigits:2});
  return String(value);
}

function formatValue(value: unknown, unit: string | null | undefined, labels: EvidencePresentation): string {
  if (value === null || value === undefined) return labels.notRecorded;
  const normalizedUnit = unit || "";
  const currencyMatch = normalizedUnit.match(/^([A-Z]{3})(?:_MONTH)?$/);
  if (currencyMatch && typeof value === "number") {
    const formatted = new Intl.NumberFormat(labels.locale, {style:"currency",currency:currencyMatch[1],maximumFractionDigits:2}).format(value);
    return normalizedUnit.endsWith("_MONTH") ? formatted + labels.perMonth : formatted;
  }
  const rendered = displayScalar(value, labels);
  if (!normalizedUnit) return rendered;
  if (normalizedUnit === "%") return rendered + "%";
  return rendered + " " + (labels.units[normalizedUnit] || normalizedUnit);
}

function displayTechnical(value: unknown, labels: EvidencePresentation): string {
  if (value === null || value === undefined) return labels.notRecorded;
  if (Array.isArray(value)) return value.length ? value.map(item=>displayTechnical(item,labels)).join(" · ") : labels.none;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length ? entries.map(([key,item])=>key+": "+displayTechnical(item,labels)).join(" · ") : labels.none;
  }
  return displayScalar(value,labels);
}

function metricValue(metric: EvidenceMetric, labels: EvidencePresentation) {
  return formatValue(metric.value,metric.unit,labels);
}

function criterionText(criterion: EvidenceCriterion, labels: EvidencePresentation) {
  const observed = criterion.observed_value === null ? labels.observedUnavailable : formatValue(criterion.observed_value,criterion.unit,labels);
  const threshold = formatValue(criterion.threshold_value,criterion.unit,labels);
  return observed+" "+criterion.operator+" "+threshold;
}

export function FindingEvidence({
  evidence,
  observedAt = null,
  collectionRunId = null,
}: Props) {
  const t = useTranslations("opportunities.evidence");
  const locale = useLocale();
  const labels: EvidencePresentation = {
    locale, notRecorded:t("notRecorded"), yes:t("yes"), no:t("no"), none:t("none"), observedUnavailable:t("observedUnavailable"), perMonth:t("perMonth"),
    units:{days:t("unit.days"),volumes:t("unit.volumes"),requests:t("unit.requests"),connections:t("unit.connections"),datapoints:t("unit.datapoints"),associations:t("unit.associations"),tags:t("unit.tags")}
  };
  if (!evidence) {
    return (
      <section className="finding-evidence" aria-label={t("aria")}>
        <h3>{t("why", {product:PRODUCT_NAME})}</h3>
        <p>{t("unavailable")}</p>
      </section>
    );
  }

  return (
    <section className="finding-evidence" aria-label={t("aria")}>
      <div className="evidence-heading">
        <div>
          <h3>{t("why", {product:PRODUCT_NAME})}</h3>
          {observedAt && <span>{t("observedAt", {date:formatDate(observedAt)})}</span>}
        </div>
        <span className="evidence-rule-name">{evidence.rule.name}</span>
      </div>

      <p className="evidence-summary">{evidence.summary}</p>
      <p className="evidence-rule-description">{evidence.rule.description}</p>

      {evidence.metrics.length > 0 && (
        <div className="evidence-metrics" aria-label={t("metricsAria")}>
          {evidence.metrics.map((metric) => (
            <div key={metric.key} className="evidence-metric">
              <span>{metric.label}</span>
              <strong>{metricValue(metric,labels)}</strong>
              {metric.kind !== "observed" && (
                <small>
                  {metric.kind === "estimate"
                    ? t("estimate")
                    : metric.kind === "projection"
                      ? t("projection")
                      : metric.kind}
                </small>
              )}
            </div>
          ))}
        </div>
      )}

      {evidence.criteria.length > 0 && (
        <div className="evidence-block">
          <h4>{t("criterion")}</h4>
          <dl className="evidence-facts">
            {evidence.criteria.map((criterion) => (
              <div key={criterion.key}>
                <dt>{criterion.label}</dt>
                <dd>{criterionText(criterion,labels)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {evidence.contributors.length > 0 && (
        <div className="evidence-block evidence-contributors">
          <h4>{t("contributors")}</h4>
          <div
            className="data-table-wrap"
            role="region"
            aria-label={t("contributorsAria")}
            tabIndex={0}
          >
            <table className="contributors-table">
              <thead>
                <tr>
                  <th scope="col">{t("contributor")}</th>
                  <th scope="col">{t("previous")}</th>
                  <th scope="col">{t("current")}</th>
                  <th scope="col">{t("delta")}</th>
                </tr>
              </thead>
              <tbody>
                {evidence.contributors.map((item) => (
                  <tr key={item.key}>
                    <th scope="row">{item.label}</th>
                    <td>{formatValue(item.previous_value, item.unit, labels)}</td>
                    <td>{formatValue(item.current_value, item.unit, labels)}</td>
                    <td>+{formatValue(item.delta, item.unit, labels)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {evidence.notes.length > 0 && (
        <ul className="evidence-notes">
          {evidence.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}

      <details className="evidence-technical">
        <summary>{t("seeTechnical")}</summary>
        <div className="evidence-columns">
          <div>
            <h4>{t("observedDetails")}</h4>
            <dl className="evidence-facts">
              {Object.entries(evidence.details).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{displayTechnical(value,labels)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <h4>{t("parameters")}</h4>
            {Object.keys(evidence.parameters).length ? (
              <dl className="evidence-facts">
                {Object.entries(evidence.parameters).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{displayTechnical(value,labels)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>{t("historicalUnavailable")}</p>
            )}
          </div>
        </div>
        {collectionRunId && (
          <p className="evidence-run-id">
            CollectionRun: <code>{collectionRunId}</code>
          </p>
        )}
      </details>

      <p className="evidence-source">
        {t("source")} {evidence.source}
        {evidence.evaluated_at ? ` · ${t("evaluatedAt", {date:formatDate(evidence.evaluated_at)})}` : ""}
      </p>
    </section>
  );
}
