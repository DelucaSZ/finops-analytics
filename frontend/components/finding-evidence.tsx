import { findingExplanation } from "@/lib/finding-explanation";
import { formatDate, usd } from "@/lib/api";
import { isStructuredEvidence } from "@/lib/opportunity-evidence.mjs";
import type {
  EvidenceCriterion,
  EvidenceMetric,
  Finding,
  OpportunityEvidence,
} from "@/lib/types";

function display(value: unknown): string {
  if (value === null || value === undefined) return "Não disponível";
  if (Array.isArray(value)) return value.map(display).join(", ") || "Nenhum";
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "number") {
    return value.toLocaleString("pt-BR", { maximumFractionDigits: 2 });
  }
  return String(value);
}

function unitLabel(unit: string | null | undefined): string {
  const labels: Record<string, string> = {
    days: "dias",
    day: "dia",
    month: "mês",
    volumes: "volumes",
    requests: "requests",
    connections: "conexões",
    datapoints: "amostras",
    tags: "tags",
  };
  return unit ? labels[unit] || unit : "";
}

function formattedValue(
  value: unknown,
  unit?: string | null,
  currency?: string | null,
): string {
  if (value === null || value === undefined) return "Não disponível";
  if (currency === "USD" && typeof value === "number") {
    const money = usd(value);
    return unit === "month" ? `${money}/mês` : money;
  }
  const base = display(value);
  const suffix = unitLabel(unit);
  return suffix ? `${base} ${suffix}` : base;
}

function MetricValue({ metric }: { metric: EvidenceMetric }) {
  return (
    <div>
      <dt>{metric.label}</dt>
      <dd>{formattedValue(metric.value, metric.unit, metric.currency)}</dd>
    </div>
  );
}

function CriterionValue({ criterion }: { criterion: EvidenceCriterion }) {
  const operator = criterion.operator && !["=", "window"].includes(criterion.operator)
    ? `${criterion.operator} `
    : "";
  return (
    <div>
      <dt>{criterion.label}</dt>
      <dd>
        {operator}
        {formattedValue(criterion.value, criterion.unit, criterion.currency)}
      </dd>
    </div>
  );
}

function technicalValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) return <span>Não disponível</span>;
  if (Array.isArray(value)) {
    if (!value.length) return <span>Nenhum</span>;
    return (
      <ul className="technical-value-list">
        {value.map((item, index) => <li key={index}>{technicalValue(item)}</li>)}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <dl className="technical-value-map">
        {Object.entries(value as Record<string, unknown>).map(([key, item]) => (
          <div key={key}>
            <dt>{key.replaceAll("_", " ")}</dt>
            <dd>{technicalValue(item)}</dd>
          </div>
        ))}
      </dl>
    );
  }
  return <span>{display(value)}</span>;
}

function StructuredEvidence({
  finding,
  evidence,
}: {
  finding: Finding;
  evidence: OpportunityEvidence;
}) {
  const contributors = Array.isArray(evidence.details.contributors)
    ? evidence.details.contributors.filter(
        (item): item is Record<string, unknown> =>
          Boolean(item && typeof item === "object" && !Array.isArray(item)),
      )
    : [];
  const technicalDetails = Object.entries(evidence.details).filter(
    ([key]) => key !== "contributors",
  );

  return (
    <section className="finding-evidence" aria-label={`Evidências de ${finding.title}`}>
      <h3>Por que o DeepOps chegou nessa conclusão?</h3>
      <p className="evidence-summary">{evidence.summary}</p>

      <div className="evidence-rule">
        <div>
          <span className="eyebrow">REGRA</span>
          <strong>{evidence.rule.name}</strong>
          <p>{evidence.rule.description}</p>
        </div>
      </div>

      <div className="evidence-columns">
        <div>
          <h4>Dados que sustentam o achado</h4>
          {evidence.metrics.length ? (
            <dl className="evidence-facts">
              {evidence.metrics.map((metric) => (
                <MetricValue key={metric.key} metric={metric} />
              ))}
            </dl>
          ) : (
            <p>Detalhes adicionais não disponíveis para esta análise.</p>
          )}
        </div>
        <div>
          <h4>Critério aplicado nesta coleta</h4>
          {evidence.rule.criteria.length ? (
            <dl className="evidence-facts">
              {evidence.rule.criteria.map((criterion) => (
                <CriterionValue key={criterion.key} criterion={criterion} />
              ))}
            </dl>
          ) : (
            <p>O threshold utilizado não foi registrado nesta análise.</p>
          )}
        </div>
      </div>

      {contributors.length > 0 && (
        <div className="evidence-contributors">
          <h4>Principais responsáveis pelo crescimento</h4>
          <div
            className="data-table-wrap"
            role="region"
            aria-label="Contribuidores de custo"
            tabIndex={0}
          >
            <table className="contributors-table">
              <thead>
                <tr>
                  <th scope="col">Dimensão</th>
                  <th scope="col">Anterior</th>
                  <th scope="col">Atual</th>
                  <th scope="col">Variação</th>
                </tr>
              </thead>
              <tbody>
                {contributors.map((item, index) => (
                  <tr key={`${String(item.name)}-${index}`}>
                    <th scope="row">{display(item.name)}</th>
                    <td>{formattedValue(item.previous_value, null, String(item.currency || ""))}</td>
                    <td>{formattedValue(item.current_value, null, String(item.currency || ""))}</td>
                    <td>
                      +{formattedValue(item.delta, null, String(item.currency || ""))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {evidence.limitations.length > 0 && (
        <div className="evidence-limitations">
          <h4>Observações sobre a evidência</h4>
          <ul className="evidence-notes">
            {evidence.limitations.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
      )}

      {technicalDetails.length > 0 && (
        <details className="evidence-technical-details">
          <summary>Ver evidência técnica</summary>
          <dl>
            {technicalDetails.map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{technicalValue(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}

      <p className="evidence-source">
        Fonte: {evidence.source.system} · Evidência registrada em{" "}
        {formatDate(evidence.source.evaluated_at)}
      </p>
    </section>
  );
}

function LegacyEvidence({
  finding,
  evidence,
}: {
  finding: Finding;
  evidence: Record<string, unknown>;
}) {
  const legacyFinding = { ...finding, evidence };
  const explanation = findingExplanation(legacyFinding);
  return (
    <section className="finding-evidence" aria-label={`Evidências de ${finding.title}`}>
      <h3>Por que o DeepOps chegou nessa conclusão?</h3>
      <p>{explanation.summary}</p>
      <div className="legacy-evidence-notice">
        Evidência registrada antes do contrato estruturado de explicabilidade.
      </div>
      <div className="evidence-columns">
        <div>
          <h4>Dados observados</h4>
          {explanation.facts.length ? (
            <dl className="evidence-facts">
              <div><dt>Recurso / agrupamento</dt><dd>{finding.resource_id}</dd></div>
              {explanation.facts.map((fact) => (
                <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
              ))}
            </dl>
          ) : (
            <p>Detalhes adicionais não disponíveis para esta análise.</p>
          )}
        </div>
        <div>
          <h4>Critérios registrados</h4>
          {explanation.criteria.length ? (
            <dl className="evidence-facts">
              {explanation.criteria.map((fact) => (
                <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
              ))}
            </dl>
          ) : (
            <p>O threshold utilizado não foi registrado nesta análise.</p>
          )}
        </div>
      </div>
      <ul className="evidence-notes">
        {explanation.notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
      <p className="evidence-source">
        Fonte: {explanation.source} · Última validação: {formatDate(finding.last_seen_at)}
      </p>
    </section>
  );
}

export function FindingEvidence({
  finding,
  evidence,
}: {
  finding: Finding;
  evidence?: unknown;
}) {
  if (isStructuredEvidence(evidence)) {
    return <StructuredEvidence finding={finding} evidence={evidence} />;
  }
  if (evidence && typeof evidence === "object" && !Array.isArray(evidence)) {
    return (
      <LegacyEvidence
        finding={finding}
        evidence={evidence as Record<string, unknown>}
      />
    );
  }
  return (
    <section className="finding-evidence" aria-label={`Evidências de ${finding.title}`}>
      <h3>Por que o DeepOps chegou nessa conclusão?</h3>
      <p>Detalhes adicionais não disponíveis para esta análise.</p>
    </section>
  );
}
