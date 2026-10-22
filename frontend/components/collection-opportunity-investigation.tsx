"use client";

import Link from "next/link";
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

const number = (value: number) => formatNumber(value);

function MetricLink({ href, label, value, title }: { href: string; label: string; value: number; title?: string }) {
  return (
    <Link className="collection-link" href={href} title={title}>
      <strong>{number(value)}</strong>
      <span>{label}</span>
    </Link>
  );
}

export function CollectionOpportunityInvestigation({ run }: { run: RunIdentity }) {
  const request = useApiQuery<RunChanges>({
    key: ["collections", run.id, "opportunity-changes"],
    path: `/collections/${encodeURIComponent(run.id)}/opportunity-changes`,
    ...cachePolicy.detail,
  });

  if (request.isLoading) return <p role="status">Carregando investigação de oportunidades…</p>;
  if (request.error || !request.data) {
    return (
      <div className="alert error" role="alert">
        Não foi possível carregar a comparação de oportunidades desta coleta.
        <button className="button ghost" onClick={() => void request.refetch()}>Tentar novamente</button>
      </div>
    );
  }

  const data = request.data;
  const scope = { provider: run.provider, accountId: run.account_id };
  const comparisonAvailable = data.comparable;

  return (
    <section aria-label="Investigação de oportunidades desta coleta">
      <div className="collection-toolbar">
        <h3>Oportunidades desta coleta</h3>
        <span>{data.comparison_status === "PARTIAL" ? "Comparação parcial" : data.comparison_status}</span>
      </div>

      {data.comparison_status === "RUNNING" && (
        <div className="alert" role="status">
          <strong>Coleta em andamento.</strong>
          <p>Observações já persistidas podem ser exibidas, mas ainda não representam o resultado definitivo.</p>
        </div>
      )}
      {data.comparison_status === "FAILED" && (
        <div className="alert error" role="status">
          <strong>Comparação indisponível.</strong>
          <p>Esta coleta falhou e não possui cobertura suficiente para comparar oportunidades.</p>
        </div>
      )}
      {data.comparison_status === "EXPIRED" && (
        <div className="alert" role="status">
          <strong>Detalhes históricos indisponíveis.</strong>
          <p>Os detalhes por oportunidade desta coleta ou da baseline expiraram pela política de retenção. O total agregado conhecido continua preservado.</p>
        </div>
      )}

      {data.target_details_available && (
        <div className="collection-metadata">
          <div>
            <dt>Observadas</dt>
            <dd><MetricLink href={buildObservedOpportunitiesHref(run.id, scope)} value={data.summary.observed} label="Ver oportunidades observadas" /></dd>
          </div>
          <div>
            <dt>Identificadas pela primeira vez</dt>
            <dd><MetricLink href={buildFirstSeenOpportunitiesHref(run.id, scope)} value={data.summary.first_seen} label="Ver novas nesta coleta" /></dd>
          </div>
          {comparisonAvailable && (
            <>
              <div>
                <dt>Novas vs coleta anterior</dt>
                <dd><MetricLink href={buildNewVsPreviousHref(run.id, scope)} value={data.summary.new_vs_previous} label="Ver novas vs coleta anterior" title="Presentes nesta execução e ausentes na coleta comparável anterior." /></dd>
              </div>
              <div>
                <dt>Reapareceram</dt>
                <dd><MetricLink href={buildReappearedHref(run.id, scope)} value={data.summary.reappeared} label="Ver reaparecidas" title="Já haviam sido detectadas antes, ficaram ausentes na baseline e voltaram nesta execução." /></dd>
              </div>
              <div>
                <dt>Continuaram presentes</dt>
                <dd><MetricLink href={buildContinuedHref(run.id, scope)} value={data.summary.continued} label="Ver continuaram presentes" /></dd>
              </div>
              <div>
                <dt>Não detectadas nesta execução</dt>
                <dd><MetricLink href={buildNoLongerDetectedHref(run.id, scope)} value={data.summary.no_longer_detected} label="Ver não detectadas" title="Somente ausências em scopes com cobertura autoritativa são classificadas." /></dd>
              </div>
            </>
          )}
        </div>
      )}

      {data.reason === "NO_BASELINE" && (
        <div className="alert" role="status">
          <strong>Sem coleta anterior comparável.</strong>
          <p>Esta é a primeira coleta comparável desta conta. Métricas relativas à execução anterior não são inferidas.</p>
        </div>
      )}

      <div className="collection-toolbar">
        <h3>Comparação com coleta anterior</h3>
        {data.baseline ? (
          <Link className="button ghost" href={`/collections/${encodeURIComponent(data.baseline.id)}`}>
            Abrir baseline
          </Link>
        ) : null}
      </div>
      {data.baseline ? (
        <dl className="collection-metadata">
          <div><dt>Baseline</dt><dd>{formatDate(data.baseline.started_at)}</dd></div>
          <div><dt>Cloud</dt><dd>{providerLabel(data.baseline.provider)}</dd></div>
          <div><dt>Conta</dt><dd>{data.baseline.account_id}</dd></div>
          <div><dt>Status</dt><dd>{data.baseline.status}</dd></div>
          <div><dt>Versão dos analyzers</dt><dd>{data.baseline.analyzer_version || "Não registrada"}</dd></div>
          <div><dt>Run</dt><dd><code>{data.baseline.id.slice(0, 8)}</code></dd></div>
        </dl>
      ) : (
        <p className="collection-note">Nenhuma baseline foi utilizada nesta execução.</p>
      )}

      <h3>Cobertura dos scopes</h3>
      <dl className="collection-metadata">
        <div><dt>Total</dt><dd>{number(data.coverage.total_scopes)}</dd></div>
        <div><dt>SUCCESS</dt><dd>{number(data.coverage.successful_scopes)}</dd></div>
        <div><dt>FAILED</dt><dd>{number(data.coverage.failed_scopes)}</dd></div>
        <div><dt>SKIPPED</dt><dd>{number(data.coverage.skipped_scopes)}</dd></div>
        <div><dt>Comparáveis</dt><dd>{number(data.coverage.comparable_scopes)}</dd></div>
      </dl>

      {data.warnings.map((warning) => (
        <div className="alert" role="status" key={warning.code}>
          <strong>{warning.code === "RULES_VERSION_CHANGED" ? "Versões de regras diferentes" : "Atenção à comparação"}</strong>
          <p>{warning.message}</p>
        </div>
      ))}

      {data.scope_issues.length > 0 && (
        <div>
          <h3>Scopes sem sucesso</h3>
          <div className="data-table-wrap" tabIndex={0} role="region" aria-label="Scopes sem sucesso">
            <table className="data-table">
              <thead><tr><th>Scope</th><th>Status</th><th>Erro</th></tr></thead>
              <tbody>
                {data.scope_issues.map((issue) => (
                  <tr key={`${issue.provider}:${issue.account_id}:${issue.region}:${issue.rule_key}`}>
                    <td>{issue.region} · {issue.service || issue.rule_key}<span>{issue.rule_key}</span></td>
                    <td>{issue.status}</td>
                    <td>{issue.error_detail || "Sem detalhe registrado"}</td>
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
