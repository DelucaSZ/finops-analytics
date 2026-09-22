import { findingExplanation } from "@/lib/finding-explanation";
import { formatDate, usd } from "@/lib/api";
import type { Finding } from "@/lib/types";

export function FindingEvidence({ finding }: { finding: Finding }) {
  const explanation = findingExplanation(finding);
  return (
    <section className="finding-evidence" aria-label={`Evidências de ${finding.title}`}>
      <h3>Por que esta oportunidade foi identificada?</h3>
      <p>{explanation.summary}</p>
      <div className="evidence-columns">
        <div>
          <h4>Dados observados</h4>
          <dl className="evidence-facts">
            <div><dt>Recurso / agrupamento</dt><dd>{finding.resource_id}</dd></div>
            {explanation.facts.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}
          </dl>
        </div>
        <div>
          <h4>Critérios aplicados nesta varredura</h4>
          {explanation.criteria.length ? <dl className="evidence-facts">
            {explanation.criteria.map((fact) => <div key={fact.label}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>)}
          </dl> : <p>Configuração dos limites não registrada nesta varredura.</p>}
        </div>
      </div>
      {explanation.contributors.length > 0 && <div className="evidence-contributors">
        <h4>Quais cobranças cresceram?</h4>
        <p>Até 5 tipos de uso com maior aumento em dólares, normalizados para o mesmo período. Reduções em outros tipos podem compensar parte destes aumentos.</p>
        <div className="data-table-wrap" role="region" aria-label="Aumento por tipo de uso" tabIndex={0}>
          <table className="contributors-table">
            <thead><tr><th scope="col">Tipo de uso informado pela AWS</th><th scope="col">Esperado</th><th scope="col">Observado</th><th scope="col">Aumento</th></tr></thead>
            <tbody>{explanation.contributors.map((item) => <tr key={item.usageType}><th scope="row">{item.usageType}</th><td>{usd(item.baseline)}</td><td>{usd(item.current)}</td><td>+{usd(item.delta)}</td></tr>)}</tbody>
          </table>
        </div>
      </div>}
      <ul className="evidence-notes">{explanation.notes.map((note) => <li key={note}>{note}</li>)}</ul>
      <p className="evidence-source">Fonte: {explanation.source} · Última validação: {formatDate(finding.last_seen_at)}</p>
    </section>
  );
}
