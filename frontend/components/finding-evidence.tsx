import { formatDate } from "@/lib/api";
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

const unitLabels: Record<string, string> = {
  days: "dias",
  volumes: "volumes",
  requests: "requisições",
  connections: "conexões",
  datapoints: "amostras",
  associations: "associações",
  tags: "tags",
};

function displayScalar(value: unknown): string {
  if (value === null || value === undefined) return "Não registrado";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "number") {
    return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  }
  return String(value);
}

function formatValue(value: unknown, unit?: string | null): string {
  if (value === null || value === undefined) return "Não registrado";
  const normalizedUnit = unit || "";
  const currencyMatch = normalizedUnit.match(/^([A-Z]{3})(?:_MONTH)?$/);
  if (currencyMatch && typeof value === "number") {
    const formatted = new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: currencyMatch[1],
      maximumFractionDigits: 2,
    }).format(value);
    return normalizedUnit.endsWith("_MONTH") ? `${formatted}/mês` : formatted;
  }
  const rendered = displayScalar(value);
  if (!normalizedUnit) return rendered;
  if (normalizedUnit === "%") return `${rendered}%`;
  return `${rendered} ${unitLabels[normalizedUnit] || normalizedUnit}`;
}

function displayTechnical(value: unknown): string {
  if (value === null || value === undefined) return "Não registrado";
  if (Array.isArray(value)) {
    if (!value.length) return "Nenhum";
    return value.map((item) => displayTechnical(item)).join(" · ");
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return "Nenhum";
    return entries.map(([key, item]) => `${key}: ${displayTechnical(item)}`).join(" · ");
  }
  return displayScalar(value);
}

function metricValue(metric: EvidenceMetric) {
  return formatValue(metric.value, metric.unit);
}

function criterionText(criterion: EvidenceCriterion) {
  const observed =
    criterion.observed_value === null
      ? "valor observado não disponível"
      : formatValue(criterion.observed_value, criterion.unit);
  const threshold = formatValue(criterion.threshold_value, criterion.unit);
  return `${observed} ${criterion.operator} ${threshold}`;
}

export function FindingEvidence({
  evidence,
  observedAt = null,
  collectionRunId = null,
}: Props) {
  if (!evidence) {
    return (
      <section className="finding-evidence" aria-label="Explicação da oportunidade">
        <h3>Por que o DeepOps chegou nessa conclusão?</h3>
        <p>Detalhes adicionais não disponíveis para esta análise.</p>
      </section>
    );
  }

  return (
    <section className="finding-evidence" aria-label="Explicação da oportunidade">
      <div className="evidence-heading">
        <div>
          <h3>Por que o DeepOps chegou nessa conclusão?</h3>
          {observedAt && <span>Evidência observada em {formatDate(observedAt)}</span>}
        </div>
        <span className="evidence-rule-name">{evidence.rule.name}</span>
      </div>

      <p className="evidence-summary">{evidence.summary}</p>
      <p className="evidence-rule-description">{evidence.rule.description}</p>

      {evidence.metrics.length > 0 && (
        <div className="evidence-metrics" aria-label="Métricas principais">
          {evidence.metrics.map((metric) => (
            <div key={metric.key} className="evidence-metric">
              <span>{metric.label}</span>
              <strong>{metricValue(metric)}</strong>
              {metric.kind !== "observed" && (
                <small>
                  {metric.kind === "estimate"
                    ? "estimativa"
                    : metric.kind === "projection"
                      ? "projeção"
                      : metric.kind}
                </small>
              )}
            </div>
          ))}
        </div>
      )}

      {evidence.criteria.length > 0 && (
        <div className="evidence-block">
          <h4>Critério aplicado nesta coleta</h4>
          <dl className="evidence-facts">
            {evidence.criteria.map((criterion) => (
              <div key={criterion.key}>
                <dt>{criterion.label}</dt>
                <dd>{criterionText(criterion)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      {evidence.contributors.length > 0 && (
        <div className="evidence-block evidence-contributors">
          <h4>Principais responsáveis pelo crescimento</h4>
          <div
            className="data-table-wrap"
            role="region"
            aria-label="Principais contribuições para a variação"
            tabIndex={0}
          >
            <table className="contributors-table">
              <thead>
                <tr>
                  <th scope="col">Contribuidor</th>
                  <th scope="col">Anterior</th>
                  <th scope="col">Atual</th>
                  <th scope="col">Variação</th>
                </tr>
              </thead>
              <tbody>
                {evidence.contributors.map((item) => (
                  <tr key={item.key}>
                    <th scope="row">{item.label}</th>
                    <td>{formatValue(item.previous_value, item.unit)}</td>
                    <td>{formatValue(item.current_value, item.unit)}</td>
                    <td>+{formatValue(item.delta, item.unit)}</td>
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
        <summary>Ver evidência técnica</summary>
        <div className="evidence-columns">
          <div>
            <h4>Detalhes observados</h4>
            <dl className="evidence-facts">
              {Object.entries(evidence.details).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>{displayTechnical(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div>
            <h4>Parâmetros usados</h4>
            {Object.keys(evidence.parameters).length ? (
              <dl className="evidence-facts">
                {Object.entries(evidence.parameters).map(([key, value]) => (
                  <div key={key}>
                    <dt>{key}</dt>
                    <dd>{displayTechnical(value)}</dd>
                  </div>
                ))}
              </dl>
            ) : (
              <p>Parâmetros históricos adicionais não disponíveis.</p>
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
        Fonte: {evidence.source}
        {evidence.evaluated_at ? ` · Avaliado em ${formatDate(evidence.evaluated_at)}` : ""}
      </p>
    </section>
  );
}
